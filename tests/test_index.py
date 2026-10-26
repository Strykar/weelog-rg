from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest


def test_indexer_handles_both_layouts(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
):
    monkeypatch.setenv("XDG_CACHE_HOME",
                       str(tmp_path_factory.mktemp("cache-outside-logs")))
    idx, stats1 = app_module.load_or_build_index(synthetic_logs)
    by_name = {Path(entry.path).name: entry for entry in idx}

    e = by_name["#channel-one.01-02.log"]
    assert (e.network, e.buffer, e.day, e.compressed) == (
        "example-network", "#channel-one", "2026-01-02", False,
    )

    e = by_name["irc.legacy-network.#oldchan.weechatlog"]
    assert (e.network, e.buffer, e.day, e.compressed) == (
        "legacy-network", "#oldchan", None, False,
    )

    assert by_name["irc.legacy-network.#oldchan.weechatlog.1.gz"].compressed

    e = by_name["core.weechat.weechatlog"]
    assert (e.network, e.buffer) == ("(core)", "weechat")

    e = by_name["irc.server.legacy-network.weechatlog"]
    assert (e.network, e.buffer) == ("legacy-network", "(server)")

    idx2, stats2 = app_module.load_or_build_index(synthetic_logs)
    assert stats1["cache_hit"] is False
    assert stats2["cache_hit"] is True
    assert [e.path for e in idx] == [e.path for e in idx2]


FILTER_CASES = [
    ("include_compressed",   ".gz"),
    ("include_system",       "core.weechat"),
    ("include_system",       "*status"),
    ("include_system",       "bouncerserv"),
    ("include_system",       "chanserv"),
]


@pytest.mark.parametrize("flag,marker", FILTER_CASES)
def test_filter_knob_excludes_and_includes(app_module, synthetic_logs,
                                            flag, marker):
    idx = app_module.build_index(synthetic_logs)

    paths_off = app_module.select_files(idx, app_module.Query())
    assert not any(marker.lower() in p.lower() for p in paths_off), (
        f"with {flag}=False, paths matching {marker!r} leaked"
    )

    q = app_module.Query(**{flag: True})
    paths_on = app_module.select_files(idx, q)
    assert any(marker.lower() in p.lower() for p in paths_on), (
        f"with {flag}=True, paths matching {marker!r} should appear"
    )


def test_system_requires_checkbox_even_when_tree_scoped(
    app_module, synthetic_logs,
):
    idx = app_module.build_index(synthetic_logs)
    paths = app_module.select_files(
        idx, app_module.Query(networks={"(core)"}),
    )
    assert paths == []


def test_date_filter_gates_dated_layout(app_module, synthetic_logs):
    idx = app_module.build_index(synthetic_logs)
    q = app_module.Query(date_from=date(2026, 1, 3))
    paths = app_module.select_files(idx, q)
    names = {Path(p).name for p in paths}
    assert "#channel-one.01-03.log" in names
    assert "#channel-one.01-02.log" not in names
    assert "alice.01-02.log" not in names


def test_corrupt_cache_rebuilds_cleanly(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
):
    cache_dir = tmp_path_factory.mktemp("cache-corrupt")
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))
    idx1, s1 = app_module.load_or_build_index(synthetic_logs)
    assert s1["cache_hit"] is False
    cp = app_module.cache_path()
    assert cp.exists()
    cp.write_text("{", encoding="utf-8")
    idx2, s2 = app_module.load_or_build_index(synthetic_logs)
    assert s2["cache_hit"] is False
    assert len(idx1) == len(idx2)


async def test_date_post_filter_handles_iso_z_lines(app_module, tmp_path):
    log = tmp_path / "irc.example-network.#chan.weechatlog"
    log.write_text(
        "2026-01-01T10:00:00.000Z\talice\tjan one\n"
        "2026-02-15T10:00:00.000Z\tbob\tfeb fifteen\n"
        "2026-03-01T10:00:00.000Z\tcarol\tmar one\n",
        encoding="utf-8",
    )
    idx = app_module.build_index(tmp_path)
    q = app_module.Query(text=":", date_to=date(2026, 2, 1))
    matches = [
        m async for m in
        app_module.run_search(q, app_module.select_files(idx, q))
    ]
    whos = sorted(m.who for m in matches)
    assert whos == ["alice"], f"ISO-Z post-filter failed: got {whos}"
