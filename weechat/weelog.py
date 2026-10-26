# SPDX-FileCopyrightText: 2026 Strykar <avinash.duduskar@gmail.com>
#
# SPDX-License-Identifier: MIT
#
# weelog: search WeeChat logs with ripgrep, from inside WeeChat.
#
#   /weelog [-nick NICK[,NICK...]] [-net NETWORK] [-chan BUFFER] [-here]
#           [-from YYYY-MM-DD] [-to YYYY-MM-DD] [-regex] [-case] [-events]
#           [-archives] [-system] [-limit N] [--] TEXT
#   /weelog -stop
#
# Upstream: https://github.com/strykar/weelog-rg
# Requires Python 3.8 or newer and ripgrep (rg) on PATH.
#
# This file imports the weelog_rg package from the checkout it lives in. The
# self-contained copy for weechat.org comes from scripts/build-weechat-script.py.

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import weechat

SCRIPT_NAME = "weelog"
SCRIPT_AUTHOR = "Strykar <avinash.duduskar@gmail.com>"
SCRIPT_VERSION = "0.1.0"
SCRIPT_LICENSE = "MIT"
SCRIPT_DESC = "Search WeeChat logs with ripgrep into a results buffer"

DEFAULT_LIMIT = 500


def _import_core() -> None:
    try:
        import weelog_rg  # noqa: F401
    except ImportError:
        # Running from a checkout: weechat/weelog.py sits one level below the package.
        # sys.path is shared with every other Python script in this WeeChat, so only
        # add the checkout when it really holds the package, and search it last.
        repo = Path(os.path.realpath(__file__)).parent.parent
        if (repo / "weelog_rg" / "__init__.py").is_file():
            sys.path.append(str(repo))
        import weelog_rg  # noqa: F401


_import_core()
from weelog_rg.index import (  # noqa: E402
    WriteRefused,
    cache_path,
    index_key,
    load_index,
    set_write_policy,
)
from weelog_rg.parse import parse_timestamp  # noqa: E402
from weelog_rg.query import Query, parse_date, select_files  # noqa: E402
from weelog_rg.search import (  # noqa: E402
    CHUNK,
    Match,
    match_from_rg,
    match_sort_key,
    rg_args,
)


class SearchError(Exception):
    pass


@dataclass
class Request:
    text: str = ""
    nick: str = ""
    network: str = ""
    channel: str = ""
    here: bool = False
    date_from: date | None = None
    date_to: date | None = None
    regex: bool = False
    case_sensitive: bool = False
    show_events: bool = False
    archives: bool = False
    system: bool = False
    limit: int = DEFAULT_LIMIT
    stop: bool = False
    error: str | None = None


_VALUE_OPTS = {
    "-nick": "nick", "-net": "network", "-chan": "channel",
    "-from": "date_from", "-to": "date_to", "-limit": "limit",
}
_FLAG_OPTS = {
    "-regex": "regex", "-case": "case_sensitive", "-events": "show_events",
    "-archives": "archives", "-system": "system", "-here": "here", "-stop": "stop",
}


def parse_command(args: str) -> Request:
    """Options come first; everything after them is the search text, verbatim."""
    req = Request()
    tokens = list(re.finditer(r"\S+", args))
    pos = 0
    i = 0
    while i < len(tokens):
        tok = tokens[i].group(0)
        if tok == "--":
            pos = tokens[i].end()
            break
        if not tok.startswith("-"):
            break
        if tok in _FLAG_OPTS:
            setattr(req, _FLAG_OPTS[tok], True)
            pos = tokens[i].end()
            i += 1
            continue
        if tok not in _VALUE_OPTS:
            req.error = f"unknown option {tok}"
            return req
        if i + 1 >= len(tokens):
            req.error = f"{tok} needs a value"
            return req
        val = tokens[i + 1].group(0)
        name = _VALUE_OPTS[tok]
        if name in ("date_from", "date_to"):
            d = parse_date(val)
            if d is None:
                req.error = f"{tok}: expected YYYY-MM-DD, got {val!r}"
                return req
            setattr(req, name, d)
        elif name == "limit":
            if not val.isdigit() or int(val) < 1:
                req.error = f"-limit: expected a positive number, got {val!r}"
                return req
            req.limit = int(val)
        else:
            setattr(req, name, val)
        pos = tokens[i + 1].end()
        i += 2
    req.text = args[pos:].strip()
    if req.stop:
        return req
    if not req.text and not req.nick.strip():
        req.error = "nothing to search: give some text or -nick NICK"
    return req


class LineBuffer:
    """Reassemble newline-terminated records from hook_process output chunks.

    WeeChat flushes the child's stdout on byte counts, so a chunk can end
    mid-line and even mid-character. A chunk that is not valid UTF-8 reaches
    the callback as bytes rather than str.
    """

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, chunk: str | bytes) -> list[bytes]:
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        self._buf += chunk
        *lines, self._buf = self._buf.split(b"\n")
        return lines

    def flush(self) -> list[bytes]:
        rest, self._buf = self._buf, b""
        return [rest] if rest else []


def hit_epoch(ts: str) -> int:
    dt = parse_timestamp(ts)
    if dt is None:
        return 0
    try:
        return int(dt.timestamp())
    except (OverflowError, OSError, ValueError):
        # Years outside what the platform's time_t can express; year 1 raises.
        return 0


@dataclass
class Search:
    request: Request
    query: Query
    paths: list[str]
    by_path: dict[str, tuple[str, str]]
    rg: list[str]
    buffer: str
    started: float = field(default_factory=time.monotonic)
    next_chunk: int = 0
    hook: str = ""
    lines: LineBuffer = field(default_factory=LineBuffer)
    hits: list[Match] = field(default_factory=list)
    rg_errors: bool = False
    err: bytes = b""
    truncated: bool = False
    stopping: bool = False


_state: dict[str, Search | None] = {"search": None}
# Index entries for the current directory key. Reloading from the cache file on
# every command cost about 200 ms on a 49k-file tree; the key costs a few stats.
_index: dict[str, tuple[list, dict[str, tuple[str, str]]]] = {}


def _current_index(logs_dir: Path) -> tuple[list, dict[str, tuple[str, str]]]:
    key = index_key(logs_dir)
    cached = _index.get(key)
    if cached is None:
        entries, key, _hit = load_index(logs_dir)
        cached = (entries, {lf.path: (lf.network, lf.buffer) for lf in entries})
        _index.clear()
        _index[key] = cached
    return cached


def _err(msg: str) -> None:
    weechat.prnt("", f"{weechat.prefix('error')}{SCRIPT_NAME}: {msg}")


def _conf(name: str) -> str:
    opt = weechat.config_get(name)
    return weechat.config_string(opt) if opt else ""


def _logs_dir() -> Path:
    raw = _conf("logger.file.path")
    if not raw:
        raise SearchError("logger.file.path is unset (is the logger plugin loaded?)")
    path = Path(weechat.string_eval_path_home(raw, {}, {}, {}))
    if not path.is_dir():
        raise SearchError(f"logger.file.path {path} is not a directory")
    return path


def _describe(req: Request) -> str:
    bits = []
    if req.text:
        bits.append(f'"{req.text}"')
    if req.nick:
        bits.append(f"nick={req.nick}")
    if req.network:
        bits.append(f"net={req.network}")
    if req.channel:
        bits.append(f"chan={req.channel}")
    if req.date_from:
        bits.append(f"from={req.date_from}")
    if req.date_to:
        bits.append(f"to={req.date_to}")
    for flag, label in (
        (req.regex, "regex"), (req.case_sensitive, "case"), (req.show_events, "events"),
        (req.archives, "archives"), (req.system, "system"),
    ):
        if flag:
            bits.append(label)
    return " ".join(bits)


def _results_buffer() -> str:
    buf = weechat.buffer_search("python", SCRIPT_NAME)
    if not buf:
        buf = weechat.buffer_new(SCRIPT_NAME, "weelog_input_cb", "", "weelog_close_cb", "")
        # Search results must never be logged back into the directory being searched.
        weechat.buffer_set(buf, "localvar_set_no_log", "1")
        weechat.buffer_set(buf, "nicklist", "0")
        weechat.buffer_set(buf, "time_for_each_line", "1")
    return buf


def _query(req: Request, index) -> Query:
    q = Query(
        text=req.text,
        regex=req.regex,
        case_sensitive=req.case_sensitive,
        date_from=req.date_from,
        date_to=req.date_to,
        nick=req.nick,
        hide_events=not req.show_events,
        include_compressed=req.archives,
        include_system=req.system,
        nick_wrap_prefix=_conf("logger.file.nick_prefix"),
        nick_wrap_suffix=_conf("logger.file.nick_suffix"),
    )
    if req.network:
        q.networks = {req.network}
    if req.channel:
        want = req.channel.casefold()
        q.buffers = {
            (lf.network, lf.buffer) for lf in index
            if lf.buffer.casefold() == want
            and (not req.network or lf.network == req.network)
        }
        if not q.buffers:
            raise SearchError(f"no logs for buffer {req.channel!r}")
        # Naming a buffer is explicit enough to override the system-buffer filter.
        q.include_system = True
    return q


def _start(req: Request) -> None:
    if _state["search"] is not None:
        _cancel()
    rg_bin = shutil.which("rg")
    if not rg_bin:
        raise SearchError("ripgrep (rg) not found on PATH")
    logs_dir = _logs_dir()
    set_write_policy(logs_dir, cache_path().parent, Path("/tmp"))
    try:
        index, by_path = _current_index(logs_dir)
    except (OSError, WriteRefused) as e:
        raise SearchError(f"cannot index {logs_dir}: {e}") from e
    q = _query(req, index)
    paths = select_files(index, q)
    rg = rg_args(q)
    if rg is None:
        raise SearchError("nothing to search")
    rg[0] = rg_bin
    buf = _results_buffer()
    weechat.buffer_clear(buf)
    weechat.buffer_set(buf, "title", f"{SCRIPT_NAME}: {_describe(req)} | searching {len(paths)} files")
    weechat.buffer_set(buf, "display", "1")
    search = Search(request=req, query=q, paths=paths, by_path=by_path, rg=rg, buffer=buf)
    _state["search"] = search
    if paths:
        _run_chunk(search)
    else:
        _finish(search)


def _run_chunk(s: Search) -> None:
    chunk = s.paths[s.next_chunk:s.next_chunk + CHUNK]
    s.next_chunk += len(chunk)
    # arg1..argN go straight to execv, so no shell splitting of patterns or paths.
    opts = {f"arg{i}": a for i, a in enumerate(s.rg[1:] + chunk, 1)}
    s.hook = weechat.hook_process_hashtable(s.rg[0], opts, 0, "weelog_process_cb", "")
    if not s.hook:
        _err("could not start rg")
        _finish(s)


def _consume(s: Search, line: bytes) -> None:
    if s.truncated:
        return
    try:
        obj = json.loads(line)
    except ValueError:
        return
    m = match_from_rg(obj, s.query)
    if m is None:
        return
    s.hits.append(m)
    if len(s.hits) >= s.request.limit:
        s.truncated = True


def _cancel() -> bool:
    s = _state["search"]
    if s is None:
        return False
    if s.hook:
        weechat.unhook(s.hook)
        s.hook = ""
    _state["search"] = None
    return True


def _finish(s: Search) -> None:
    _state["search"] = None
    if s.hook:
        weechat.unhook(s.hook)
        s.hook = ""
    s.hits.sort(key=match_sort_key)
    buf = s.buffer
    dim = weechat.color("darkgray")
    where = weechat.color("chat_buffer")
    reset = weechat.color("reset")
    for m in s.hits:
        net, chan = s.by_path.get(m.path, ("?", os.path.basename(m.path)))
        if m.is_event:
            prefix = f"{dim}{m.who}"
        else:
            prefix = f"{weechat.info_get('nick_color', m.who)}{m.who}"
        weechat.prnt_date_tags(
            buf, hit_epoch(m.timestamp), "no_highlight,notify_none,no_log",
            f"{prefix}\t{where}{net}/{chan}{reset} {m.message}",
        )
    elapsed = time.monotonic() - s.started
    n = len(s.hits)
    summary = f"{n} hit{'s' if n != 1 else ''} in {elapsed:.2f}s"
    if s.truncated:
        summary += f", stopped at -limit {s.request.limit}, narrow the search to see the rest"
    if s.rg_errors:
        err_lines = s.err.decode("utf-8", "replace").strip().splitlines()
        summary += f" (rg: {err_lines[-1].strip()})" if err_lines else " (rg could not read some files)"
    weechat.prnt_date_tags(buf, 0, "no_highlight,notify_none,no_log",
                           f"{weechat.prefix('network')}{summary}")
    weechat.buffer_set(buf, "title", f"{SCRIPT_NAME}: {_describe(s.request)} | {summary}")


def weelog_process_cb(data: str, command: str, rc: int, out: str | bytes, err: str | bytes) -> int:
    s = _state["search"]
    if s is None:
        return weechat.WEECHAT_RC_OK
    if out:
        for line in s.lines.feed(out):
            _consume(s, line)
    if err:
        s.err += err if isinstance(err, bytes) else err.encode("utf-8")
    if rc == weechat.WEECHAT_HOOK_PROCESS_ERROR:
        s.hook = ""
        _err(f"rg failed to start: {err!r}")
        _finish(s)
        return weechat.WEECHAT_RC_OK
    if rc >= 0:
        # The process has ended; WeeChat frees this hook itself once we return.
        s.hook = ""
        for line in s.lines.flush():
            _consume(s, line)
        # rg exits 1 for "no matches" and 2 for errors. --no-messages silences
        # unreadable files, so anything left on stderr is about the pattern and
        # would fail every remaining chunk the same way.
        if rc >= 2:
            s.rg_errors = True
        if s.truncated or s.next_chunk >= len(s.paths) or (rc >= 2 and s.err):
            _finish(s)
        else:
            _run_chunk(s)
        return weechat.WEECHAT_RC_OK
    if s.truncated and not s.stopping:
        # Unhooking a process hook from inside its own callback aborted WeeChat in
        # testing, so rg is stopped from a one-shot timer instead.
        s.stopping = True
        weechat.hook_timer(1, 0, 1, "weelog_stop_cb", "")
    return weechat.WEECHAT_RC_OK


def weelog_stop_cb(data: str, remaining_calls: int) -> int:
    s = _state["search"]
    if s is not None and s.stopping:
        _finish(s)
    return weechat.WEECHAT_RC_OK


def weelog_cmd_cb(data: str, buffer: str, args: str) -> int:
    req = parse_command(args)
    if req.error:
        _err(f"{req.error} (see /help {SCRIPT_NAME})")
        return weechat.WEECHAT_RC_ERROR
    if req.stop:
        weechat.prnt("", f"{SCRIPT_NAME}: " + ("search stopped" if _cancel() else "no search running"))
        return weechat.WEECHAT_RC_OK
    if req.here:
        server = weechat.buffer_get_string(buffer, "localvar_server")
        channel = weechat.buffer_get_string(buffer, "localvar_channel")
        if not server or not channel:
            _err("-here only works from an IRC channel or private buffer")
            return weechat.WEECHAT_RC_ERROR
        req.network, req.channel = server, channel
    try:
        _start(req)
    except SearchError as e:
        _err(str(e))
        return weechat.WEECHAT_RC_ERROR
    return weechat.WEECHAT_RC_OK


def weelog_input_cb(data: str, buffer: str, input_data: str) -> int:
    weechat.command(buffer, f"/{SCRIPT_NAME} {input_data}")
    return weechat.WEECHAT_RC_OK


def weelog_close_cb(data: str, buffer: str) -> int:
    _cancel()
    return weechat.WEECHAT_RC_OK


def weelog_unload_cb() -> int:
    _cancel()
    return weechat.WEECHAT_RC_OK


HELP = """\
Searches the files under logger.file.path with ripgrep and prints the hits
into a "weelog" buffer, oldest first, with the logged timestamp in the time
column and the nick coloured as WeeChat would colour it.

Options come before the text. Everything after the options is the search
text, taken verbatim (quotes are literal). Use -- when the text itself
starts with a dash.

   -nick: only lines said by NICK (comma separated for several). Fuzzy:
          every typed character must appear in the nick, in order
    -net: only this network (the name used in the log file names)
   -chan: only this channel or private buffer (case-insensitive)
   -here: shorthand for -net/-chan of the buffer the command is run from
   -from: ignore hits before this day (YYYY-MM-DD)
     -to: ignore hits after this day
  -regex: treat TEXT as a regular expression (default: fixed string)
   -case: case sensitive (default: any case)
 -events: include joins, parts, quits and other status lines
-archives: include rotated .gz/.zst archives
 -system: include server, services, bouncer and monitor buffers
  -limit: stop after N hits (default 500)
   -stop: cancel the running search

A search needs text or -nick. Typing into the weelog buffer runs the same
command again with what you typed.

Examples:
  /weelog -nick alice -from 2026-01-01 kernel panic
  /weelog -here -regex (merged|closed) PR #
  /weelog -net libera -chan #archlinux -events -- -Syu
"""


def main() -> None:
    if not weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
                            SCRIPT_DESC, "weelog_unload_cb", ""):
        return
    weechat.hook_command(
        SCRIPT_NAME,
        SCRIPT_DESC,
        "[-nick NICK[,NICK...]] [-net NETWORK] [-chan BUFFER] [-here] "
        "[-from YYYY-MM-DD] [-to YYYY-MM-DD] [-regex] [-case] [-events] "
        "[-archives] [-system] [-limit N] [--] TEXT || -stop",
        HELP,
        "-nick|-net|-chan|-here|-from|-to|-regex|-case|-events|-archives|-system|-limit|-stop",
        "weelog_cmd_cb", "",
    )


if __name__ == "__main__":
    main()
