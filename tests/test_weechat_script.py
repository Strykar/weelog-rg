from __future__ import annotations

import importlib.util
import json
import sys
from unittest.mock import MagicMock
from datetime import date, datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "weechat" / "weelog.py"


@pytest.fixture(scope="module")
def weelog():
    # The script imports the weechat module, which only exists inside WeeChat.
    stub = MagicMock(name="weechat")
    stub.WEECHAT_RC_OK = 0
    stub.WEECHAT_RC_ERROR = -1
    stub.WEECHAT_HOOK_PROCESS_RUNNING = -1
    stub.WEECHAT_HOOK_PROCESS_ERROR = -2
    saved = sys.modules.get("weechat")
    sys.modules["weechat"] = stub
    try:
        spec = importlib.util.spec_from_file_location("weelog_script", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        # dataclasses resolve postponed annotations through sys.modules.
        sys.modules["weelog_script"] = mod
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop("weelog_script", None)
        if saved is None:
            del sys.modules["weechat"]
        else:
            sys.modules["weechat"] = saved


def test_parse_command_text_only(weelog):
    req = weelog.parse_command("good morning")
    assert req.error is None
    assert req.text == "good morning"
    assert req.nick == ""
    assert req.limit == 500


def test_parse_command_options_then_text(weelog):
    req = weelog.parse_command(
        "-nick alice,bob -net libera -chan #arch -from 2026-01-01 -to 2026-01-31 "
        "-regex -case -events -archives -system -limit 50 foo.*bar"
    )
    assert req.error is None
    assert req.nick == "alice,bob"
    assert req.network == "libera"
    assert req.channel == "#arch"
    assert req.date_from == date(2026, 1, 1)
    assert req.date_to == date(2026, 1, 31)
    assert req.regex and req.case_sensitive and req.show_events
    assert req.archives and req.system
    assert req.limit == 50
    assert req.text == "foo.*bar"


def test_parse_command_text_is_taken_verbatim(weelog):
    req = weelog.parse_command("-nick alice don't  stop -- now")
    assert req.text == "don't  stop -- now"


def test_parse_command_double_dash_ends_options(weelog):
    req = weelog.parse_command("-- -nick is literal")
    assert req.error is None
    assert req.text == "-nick is literal"
    assert req.nick == ""


def test_parse_command_here_and_stop_flags(weelog):
    assert weelog.parse_command("-here foo").here
    assert weelog.parse_command("-stop").stop
    assert weelog.parse_command("-stop").error is None


@pytest.mark.parametrize("args", [
    "-bogus x",
    "-from notadate x",
    "-limit many x",
    "-limit 0 x",
    "-nick",
    "",
    "   ",
])
def test_parse_command_errors(weelog, args):
    assert weelog.parse_command(args).error


def test_parse_command_nick_alone_is_enough(weelog):
    assert weelog.parse_command("-nick alice").error is None


def test_line_buffer_reassembles_split_chunks(weelog):
    lb = weelog.LineBuffer()
    line = '{"a": "καλημέρα"}\n'.encode()
    cut = line.index("κ".encode()) + 1  # split inside the two-byte κ
    # WeeChat hands a chunk that is not valid UTF-8 to the callback as bytes.
    assert lb.feed(line[:cut]) == []
    assert lb.feed(line[cut:]) == [line[:-1]]
    # Valid chunks arrive as str and may carry several lines plus a tail.
    assert lb.feed('{"b": 1}\n{"c": 2}\n{"d"') == [b'{"b": 1}', b'{"c": 2}']
    assert lb.flush() == [b'{"d"']
    assert lb.flush() == []


def test_hit_epoch(weelog):
    assert weelog.hit_epoch("2026-01-02 10:00:30") == int(
        datetime(2026, 1, 2, 10, 0, 30).timestamp()
    )
    assert weelog.hit_epoch("2026-01-02T10:00:30Z") == int(
        datetime.fromisoformat("2026-01-02T10:00:30+00:00").timestamp()
    )
    assert weelog.hit_epoch("garbage") == 0
    assert weelog.hit_epoch("0001-01-01 00:00:00") == 0  # datetime.timestamp() raises


def _rg_json(*texts: str) -> str:
    records = [
        {"type": "match", "data": {"path": {"text": "/l/2026/net/#c.01-02.log"},
                                   "line_number": i, "lines": {"text": t}}}
        for i, t in enumerate(texts, 1)
    ]
    return "".join(json.dumps(r) + "\n" for r in records)


def _search(weelog, args: str, hook: str = "0xhook", paths=("/l/a", "/l/b")):
    req = weelog.parse_command(args)
    s = weelog.Search(request=req, query=weelog.Query(text=req.text), paths=list(paths),
                      by_path={}, rg=["/usr/bin/rg", "-e", req.text], buffer="0xbuf", hook=hook)
    weelog._state["search"] = s
    return s


def test_process_cb_stops_a_truncated_search_from_a_timer_not_the_callback(weelog):
    weechat = sys.modules["weechat"]
    weechat.reset_mock()
    s = _search(weelog, "-limit 1 hello")
    out = _rg_json("2026-01-02 10:00:00\talice\thello\n",
                   "2026-01-02 10:00:01\tbob\thello again\n")
    rc = weelog.weelog_process_cb("", "rg", weechat.WEECHAT_HOOK_PROCESS_RUNNING, out, "")
    assert rc == weechat.WEECHAT_RC_OK
    assert s.truncated and len(s.hits) == 1
    weechat.unhook.assert_not_called()
    weechat.hook_timer.assert_called_once()
    assert weelog._state["search"] is s
    # More output before the timer fires must not arm a second timer.
    weelog.weelog_process_cb("", "rg", weechat.WEECHAT_HOOK_PROCESS_RUNNING, out, "")
    weechat.hook_timer.assert_called_once()
    weelog.weelog_stop_cb("", 0)
    weechat.unhook.assert_called_once_with("0xhook")
    assert weelog._state["search"] is None


def test_process_cb_at_process_end_never_unhooks(weelog):
    weechat = sys.modules["weechat"]
    weechat.reset_mock()
    # Last chunk, rg exit 1 (no matches): finish without touching the hook.
    s = _search(weelog, "hello")
    s.next_chunk = len(s.paths)
    weelog.weelog_process_cb("", "rg", 1, "", "")
    weechat.unhook.assert_not_called()
    assert weelog._state["search"] is None
    # Truncated and ended in the same callback: still no unhook.
    s = _search(weelog, "-limit 1 hello")
    s.next_chunk = 1
    weelog.weelog_process_cb("", "rg", 0, _rg_json("2026-01-02 10:00:00\talice\thello\n"), "")
    weechat.unhook.assert_not_called()
    weechat.hook_process_hashtable.assert_not_called()
    assert weelog._state["search"] is None


def test_process_cb_runs_the_next_chunk_when_one_ends(weelog):
    weechat = sys.modules["weechat"]
    weechat.reset_mock()
    s = _search(weelog, "hello", paths=("/l/a", "/l/b"))
    s.next_chunk = 1
    weelog.weelog_process_cb("", "rg", 1, "", "")
    weechat.unhook.assert_not_called()
    weechat.hook_process_hashtable.assert_called_once()
    cmd, opts = weechat.hook_process_hashtable.call_args.args[:2]
    assert cmd == "/usr/bin/rg"
    assert [opts[f"arg{i}"] for i in range(1, len(opts) + 1)] == ["-e", "hello", "/l/b"]
    assert weelog._state["search"] is s and s.next_chunk == 2


def test_process_cb_reports_a_bad_pattern_once_and_stops(weelog):
    weechat = sys.modules["weechat"]
    weechat.reset_mock()
    s = _search(weelog, "-regex ^(oops", paths=("/l/a", "/l/b", "/l/c"))
    s.next_chunk = 1
    weelog.weelog_process_cb("", "rg", 2, "",
                             "regex parse error:\n    ^(oops\n    ^\nerror: unclosed group\n")
    weechat.hook_process_hashtable.assert_not_called()
    assert weelog._state["search"] is None
    title = weechat.buffer_set.call_args.args[2]
    assert "rg: error: unclosed group" in title
    assert "could not read" not in title


def test_process_cb_unreadable_files_do_not_stop_the_search(weelog):
    weechat = sys.modules["weechat"]
    weechat.reset_mock()
    s = _search(weelog, "hello", paths=("/l/a", "/l/b"))
    s.next_chunk = 1
    weelog.weelog_process_cb("", "rg", 2, "", "")  # --no-messages: nothing on stderr
    weechat.hook_process_hashtable.assert_called_once()
    assert weelog._state["search"] is s and s.rg_errors
