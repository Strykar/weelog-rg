from __future__ import annotations

import os
import stat
import uuid
from pathlib import Path

import pytest


def test_parse_line_strips_terminal_controls(app_module):
    ts, who, msg, _ = app_module.parse_line(
        "2026-01-02 10:00:00\tal\x1bice\thi \x1b]0;title\x07 \x1b[31mred\x9b2J\tx\n"
    )
    assert who == "alice"
    assert msg == "hi ]0;title [31mred2J\tx"


async def test_buffer_names_are_not_markup(
    app_module, tmp_path, tmp_path_factory, monkeypatch, debounce_immediate,
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    name = "#[@click=app.bell]x"
    dated = tmp_path / "2026" / "net"
    dated.mkdir(parents=True)
    (dated / f"{name}.01-02.log").write_text(
        "2026-01-02 10:00:00\tbob\thello\n", encoding="utf-8",
    )
    from textual.widgets import Input, Static, Tree
    idx, stats = app_module.load_or_build_index(tmp_path)
    app = app_module.Hindsight(tmp_path, idx, theme="dark", index_stats=stats)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)
        tree = app.query_one("#tree", Tree)
        assert name in str(tree.root.children[0].children[0].label)
        app.query_one("#q-text", Input).value = "hello"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        await pilot.pause(0.4)
        title = app.query_one("#preview-title", Static).render()
        assert name in str(title)


async def test_relative_logs_dir_starting_with_dash(app_module, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dated = Path("-logs") / "2026" / "net"
    dated.mkdir(parents=True)
    (dated / "#c.01-02.log").write_text(
        "2026-01-02 10:00:00\tbob\thello\n", encoding="utf-8",
    )
    idx = app_module.build_index(Path("-logs"))
    assert all(os.path.isabs(e.path) for e in idx)
    q = app_module.Query(text="hello")
    matches = [
        m async for m in
        app_module.run_search(q, app_module.select_files(idx, q))
    ]
    assert [m.who for m in matches] == ["bob"]


@pytest.fixture
def export_path(app_module, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    p = Path("/tmp") / f"weelog-hindsight-test-{uuid.uuid4().hex}.tsv"
    yield p
    if p.exists() or p.is_symlink():
        p.unlink()


def test_export_is_private(app_module, export_path):
    with app_module.open_w(export_path, exclusive=True, encoding="utf-8") as f:
        f.write("x")
    assert stat.S_IMODE(export_path.stat().st_mode) == 0o600


def test_export_refuses_existing_file(app_module, export_path):
    export_path.write_text("planted", encoding="utf-8")
    with pytest.raises(FileExistsError):
        app_module.open_w(export_path, exclusive=True, encoding="utf-8")
    assert export_path.read_text(encoding="utf-8") == "planted"


def test_index_skips_dated_file_with_impossible_date(app_module, tmp_path):
    dated = tmp_path / "2026" / "net"
    dated.mkdir(parents=True)
    (dated / "#c.13-40.log").write_text("2026-01-02 10:00:00\tbob\thello\n", encoding="utf-8")
    (dated / "#c.01-02.log").write_text("2026-01-02 10:00:00\tbob\thello\n", encoding="utf-8")
    idx = app_module.build_index(tmp_path)
    assert [e.day for e in idx] == ["2026-01-02"]
    assert len(app_module.select_files(idx, app_module.Query(text="hello"))) == 1


_OSC_TITLE = "\x1b]0;PWNED\x1b\\"


async def test_buffer_names_are_not_terminal_controls(
    app_module, tmp_path, tmp_path_factory, monkeypatch, debounce_immediate,
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    dated = tmp_path / "2026" / f"net{_OSC_TITLE}"
    dated.mkdir(parents=True)
    (dated / f"#chan{_OSC_TITLE}.01-02.log").write_text(
        "2026-01-02 10:00:00\tbob\thello\n", encoding="utf-8",
    )
    from textual.widgets import DataTable, Input, Static, Tree
    idx, stats = app_module.load_or_build_index(tmp_path)
    app = app_module.Hindsight(tmp_path, idx, theme="dark", index_stats=stats)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)
        net_node = app.query_one("#tree", Tree).root.children[0]
        shown = [str(net_node.label), str(net_node.children[0].label)]
        app.query_one("#q-text", Input).value = "hello"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        await pilot.pause(0.4)
        shown.append(str(app.query_one("#results", DataTable).get_row_at(0)[2]))
        shown.append(str(app.query_one("#preview-title", Static).render()))
    for s in shown:
        assert "\x1b" not in s, repr(s)
    assert shown[2] == "#chan]0;PWNED\\"


async def test_non_utf8_filenames_are_searchable(
    app_module, tmp_path, tmp_path_factory, monkeypatch, debounce_immediate,
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    dated = tmp_path / "2026" / "net"
    dated.mkdir(parents=True)
    line = "2026-01-02 10:00:00\tbob\thello\n"
    (dated / os.fsdecode(b"#ch\xff.01-02.log")).write_text(line, encoding="utf-8")
    (tmp_path / os.fsdecode(b"irc.net.#old\xff.weechatlog")).write_text(line, encoding="utf-8")
    from textual.widgets import DataTable, Input
    idx, stats = app_module.load_or_build_index(tmp_path)
    app = app_module.Hindsight(tmp_path, idx, theme="dark", index_stats=stats)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)
        app.query_one("#q-text", Input).value = "hello"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        await pilot.pause(0.4)
        dt = app.query_one("#results", DataTable)
        assert dt.row_count == 2
        assert {str(dt.get_row_at(i)[2]) for i in range(2)} == {"#ch�", "#old�"}
