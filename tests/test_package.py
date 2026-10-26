from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from weelog_rg.index import build_index, classify_buffer, index_key, load_index
from weelog_rg.parse import context_groups, context_records, parse_line
from weelog_rg.query import Query, parse_date, select_files
from weelog_rg.search import Match, match_from_rg, rg_args, run_search

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE = ["rg", "--json", "-z", "--no-messages", "-C", "0"]
CORE_MODULES = (
    "weelog_rg", "weelog_rg.parse", "weelog_rg.index", "weelog_rg.query",
    "weelog_rg.search", "weelog_rg.cli",
)


@pytest.mark.parametrize("mod", CORE_MODULES)
def test_core_module_imports_without_ui_deps(mod):
    # A WeeChat plugin runs in an interpreter that has neither textual nor rich.
    code = (
        f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r}); import {mod}; "
        "print(sorted(m for m in sys.modules "
        "if m.split('.')[0] in ('rich', 'textual')))"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "[]"


def test_rg_args_fixed_string_ignores_case_by_default():
    assert rg_args(Query(text="hello")) == BASE + ["-i", "-F", "-e", "hello"]


def test_rg_args_regex_case_sensitive():
    q = Query(text="h.llo", regex=True, case_sensitive=True)
    assert rg_args(q) == BASE + ["-e", "h.llo"]


def test_rg_args_nothing_to_search():
    assert rg_args(Query()) is None
    assert rg_args(Query(text="   ")) is not None  # whitespace is a pattern
    assert rg_args(Query(text="", nick="  ")) is None


def test_rg_args_nick_anchor_matches_only_the_nick_column():
    args = rg_args(Query(text="morning", nick="alice"))
    assert "-F" not in args
    pattern = args[-1]
    assert re.search(pattern, "2026-01-02 10:00:30\talice\tgood morning")
    assert not re.search(pattern, "2026-01-02 10:00:30\tbob\tgood morning")
    assert not re.search(pattern, "2026-01-02 10:00:30\talice\tgood evening")
    assert not re.search(pattern, "2026-01-02 10:00:30\tbob\talice said morning")


def test_rg_args_nick_alone_drives_the_search():
    args = rg_args(Query(nick="alice"))
    assert args is not None
    assert re.search(args[-1], "2026-01-02 10:00:30\talice\tanything")


def test_rg_args_nick_wrappers_are_part_of_the_anchor():
    args = rg_args(Query(nick="alice", nick_wrap_prefix="<", nick_wrap_suffix=">"))
    assert re.search(args[-1], "2026-01-02 10:00:30\t<alice>\thi")
    assert not re.search(args[-1], "2026-01-02 10:00:30\talice\thi")


def _rg_match(path: str, line_no: int, text: str) -> dict:
    return {
        "type": "match",
        "data": {
            "path": {"text": path},
            "line_number": line_no,
            "lines": {"text": text},
            "absolute_offset": 0,
            "submatches": [],
        },
    }


def test_match_from_rg_chat_line():
    obj = _rg_match("/l/2026/net/#c.01-02.log", 3,
                    "2026-01-02 10:00:30\talice\tgood morning\n")
    assert match_from_rg(obj, Query(text="morning")) == Match(
        "/l/2026/net/#c.01-02.log", 3, "2026-01-02 10:00:30", "alice",
        "good morning", False,
    )


def test_match_from_rg_ignores_non_match_records():
    q = Query(text="x")
    assert match_from_rg({"type": "begin", "data": {"path": {"text": "/x"}}}, q) is None
    assert match_from_rg({"type": "end", "data": {}}, q) is None
    assert match_from_rg({"type": "summary", "data": {}}, q) is None


def test_match_from_rg_hides_events_by_default():
    obj = _rg_match("/x.log", 1, "2026-01-02 10:00:00\t-->\talice has joined\n")
    assert match_from_rg(obj, Query(text="joined")) is None
    m = match_from_rg(obj, Query(text="joined", hide_events=False))
    assert m is not None and m.is_event and m.who == "-->"


def test_match_from_rg_date_window():
    obj = _rg_match("/x.weechatlog", 1, "2026-01-02 10:00:00\talice\thello\n")
    assert match_from_rg(obj, Query(text="hello", date_from=date(2026, 1, 3))) is None
    assert match_from_rg(obj, Query(text="hello", date_to=date(2026, 1, 1))) is None
    q = Query(text="hello", date_from=date(2026, 1, 1), date_to=date(2026, 1, 2))
    assert match_from_rg(obj, q) is not None


def test_match_from_rg_keeps_unparseable_timestamps_inside_a_date_window():
    obj = _rg_match("/x.weechatlog", 1, "garbage\talice\thello\n")
    q = Query(text="hello", date_from=date(2026, 1, 1))
    assert match_from_rg(obj, q) is not None


def test_match_from_rg_strips_nick_wrappers():
    obj = _rg_match("/x.log", 1, "2026-01-02 10:00:00\t<alice>\thello\n")
    q = Query(text="hello", nick_wrap_prefix="<", nick_wrap_suffix=">")
    assert match_from_rg(obj, q).who == "alice"


def test_match_from_rg_decodes_base64_paths():
    raw = b"/l/irc.net.\xff.weechatlog"
    obj = {
        "type": "match",
        "data": {
            "path": {"bytes": base64.b64encode(raw).decode()},
            "line_number": 1,
            "lines": {"text": "2026-01-02 10:00:00\talice\thello\n"},
        },
    }
    assert match_from_rg(obj, Query(text="hello")).path == os.fsdecode(raw)


async def _hits(q, logs):
    idx = build_index(logs)
    return [m async for m in run_search(q, select_files(idx, q))]


async def test_search_ignores_case_unless_asked(synthetic_logs):
    # Capitals in the text or in a nick typed as displayed must not make it case sensitive.
    assert len(await _hits(Query(text="GOOD Morning"), synthetic_logs)) == 1
    assert len(await _hits(Query(text="MORNING", nick="Alice"), synthetic_logs)) == 1
    assert await _hits(Query(text="GOOD Morning", case_sensitive=True), synthetic_logs) == []
    assert len(await _hits(Query(text="good morning", case_sensitive=True), synthetic_logs)) == 1


async def test_run_search_through_the_package(synthetic_logs):
    idx = build_index(synthetic_logs)
    q = Query(text="morning", nick="alice")
    matches = [m async for m in run_search(q, select_files(idx, q))]
    assert matches
    assert all(m.who == "alice" and "morning" in m.message for m in matches)


def test_load_index_reuses_the_cache_and_exposes_its_key(synthetic_logs):
    idx1, key1, hit1 = load_index(synthetic_logs)
    idx2, key2, hit2 = load_index(synthetic_logs)
    assert (hit1, hit2) == (False, True)
    assert idx1 == idx2 and key1 == key2 == index_key(synthetic_logs)
    (synthetic_logs / "irc.new-network.#fresh.weechatlog").write_text(
        "2026-01-02 10:00:00\talice\thello\n", encoding="utf-8")
    assert index_key(synthetic_logs) != key1
    idx3, _key3, hit3 = load_index(synthetic_logs)
    assert hit3 is False and len(idx3) == len(idx1) + 1


def _ten_line_log(tmp_path):
    p = tmp_path / "irc.net.#c.weechatlog"
    lines = []
    for i in range(1, 11):
        who, msg = ("-->", f"someone joined {i}") if i in (4, 7) else ("alice", f"message {i}")
        lines.append(f"2026-01-02 10:00:{i:02d}\t{who}\t{msg}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def test_context_groups_merges_touching_ranges_and_marks_hits(tmp_path):
    path = _ten_line_log(tmp_path)
    groups = context_groups(path, [3, 5], span=1, hide_events=True)
    assert [[(r[0], r[5]) for r in g] for g in groups] == [
        [(2, False), (3, True), (5, True), (6, False)],   # line 4 is a hidden event
    ]
    groups = context_groups(path, [2, 8], span=1, hide_events=True)
    assert [[r[0] for r in g] for g in groups] == [[1, 2, 3], [8, 9]]  # 7 is an event
    groups = context_groups(path, [8, 2], span=1, hide_events=False)
    assert [[r[0] for r in g] for g in groups] == [[1, 2, 3], [7, 8, 9]]
    assert groups[1][0][4] is True and groups[1][0][5] is False  # event shown as context


def test_context_groups_keeps_an_event_that_is_itself_a_hit(tmp_path):
    path = _ten_line_log(tmp_path)
    groups = context_groups(path, [4], span=0, hide_events=True)
    assert [(r[0], r[2], r[4], r[5]) for r in groups[0]] == [(4, "-->", True, True)]


def test_context_groups_edges(tmp_path):
    path = _ten_line_log(tmp_path)
    assert context_groups(path, [], 3, True) == []
    assert context_groups(str(tmp_path / "missing"), [1], 3, True) == []
    assert [r[0] for r in context_groups(path, [1], span=2, hide_events=True)[0]] == [1, 2, 3]
    assert [r[0] for r in context_groups(path, [10], span=2, hide_events=True)[0]] == [8, 9, 10]
    assert context_records(path, 3, 1, True) == [r[:5] for r in context_groups(path, [3], 1, True)[0]]


def test_parse_date():
    assert parse_date("2026-01-02") == date(2026, 1, 2)
    assert parse_date(" 2026-01-02 ") == date(2026, 1, 2)
    assert parse_date("") is None
    assert parse_date("yesterday") is None


@pytest.mark.parametrize("raw", [
    "2026-01-02 10:00:30\talice\tgood morning\n",
    "2026-01-02 10:00:00\t-->\tjoined\twith\textra\ttabs\n",
    "no tabs at all",
    "\x1932alice\x1c\tbob\t\x19F05hi\n",
])
def test_parse_line_matches_the_tui_copy(app_module, raw):
    # Until bin/weelog-rg becomes a shim over the package, the two copies must agree.
    assert parse_line(raw) == app_module.parse_line(raw)


@pytest.mark.parametrize("network,buffer", [
    ("libera", "#arch"), ("libera", "alice"), ("libera", "(server)"),
    ("libera", "*status"), ("libera", "ChanServ"), ("libera", "BouncerServ"),
    ("(core)", "weechat"), ("(core)", "highmon"), ("(core)", "other"),
])
def test_classify_buffer_matches_the_tui_copy(app_module, network, buffer):
    assert classify_buffer(network, buffer) == app_module.classify_buffer(network, buffer)
