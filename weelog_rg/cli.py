"""Non-interactive search: one line per hit on stdout, for scripts and pipelines."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import sys
import zlib
from datetime import date
from pathlib import Path

from .index import LogFile, WriteRefused, cache_path, load_index, set_write_policy
from .parse import context_records, extract_hms, read_weechat_nick_wrappers
from .query import Query, parse_date, select_files
from .search import Match, match_sort_key, run_search

# Same palette and hash as the TUI, so a nick has one colour everywhere.
NICK_PALETTE = (39, 45, 51, 75, 81, 111, 117, 147, 153, 183, 189, 215, 221, 222, 228, 229)
DIM = "\x1b[2m"
RESET = "\x1b[0m"
DEFAULT_LIMIT = 500

EPILOG = """\
Output formats:
  text   TIMESTAMP  NETWORK/BUFFER  <NICK> MESSAGE; nick coloured on a terminal
  json   one object per line: timestamp, network, buffer, nick, message, event,
         path, line, plus context when --context is set
  tsv    timestamp, network, buffer, nick, message, path, line, event (0/1);
         tabs inside a field become spaces. Meant for cut/awk, not spreadsheets.

A search needs --search and/or --user. Search text that starts with a dash is
written --search=-Syu. Patterns run against the whole log line (timestamp, nick
and message, tab separated), so ^ anchors at the timestamp. Output stops after
--limit hits (default 500, 0 for all) with a note on stderr.
Exit status: 0 hits found, 1 none, 2 error.
"""


def nick_color_index(nick: str) -> int:
    return NICK_PALETTE[zlib.crc32(nick.encode("utf-8")) % len(NICK_PALETTE)]


def display_path(path: str) -> str:
    # Index paths keep undecodable bytes as surrogates; stdout and JSON cannot carry them.
    return path.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _date_arg(s: str) -> date:
    d = parse_date(s)
    if d is None:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {s!r}")
    return d


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m weelog_rg",
        description="Search a WeeChat logs directory with ripgrep and print the hits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    ap.add_argument("--logs", type=Path, metavar="DIR",
                    help="weechat logs directory (default: $WEELOG_DIR)")
    ap.add_argument("-u", "--user", action="append", default=[], metavar="NICK",
                    help="only lines said by NICK; repeatable; fuzzy, typed characters in order")
    ap.add_argument("-s", "--search", metavar="TEXT", help="text to find (fixed string)")
    ap.add_argument("--regex", action="store_true", help="treat TEXT as a regular expression")
    ap.add_argument("--case", action="store_true", help="case sensitive (default: any case)")
    ap.add_argument("--network", action="append", default=[], metavar="NET",
                    help="only this network; repeatable")
    ap.add_argument("--channel", action="append", default=[], metavar="BUFFER",
                    help="only this channel or private buffer; repeatable, any case")
    ap.add_argument("--from", dest="date_from", type=_date_arg, metavar="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", type=_date_arg, metavar="YYYY-MM-DD")
    ap.add_argument("--events", action="store_true",
                    help="include joins, parts, quits and other status lines")
    ap.add_argument("--archives", action="store_true", help="include rotated .gz/.zst archives")
    ap.add_argument("--system", action="store_true",
                    help="include server, services, bouncer and monitor buffers")
    ap.add_argument("--context", type=int, default=0, metavar="N",
                    help="lines of context around each hit (text and json)")
    ap.add_argument("--format", choices=("text", "json", "tsv"), default="text")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, metavar="N",
                    help="stop after N hits (default: %(default)s, 0 for all)")
    ap.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    return ap


def _want_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _nick(who: str, is_event: bool, color: bool) -> str:
    if not who:
        return ""
    if is_event:
        return f"{DIM}{who}{RESET}" if color else who
    shown = f"<{who}>"
    return f"\x1b[38;5;{nick_color_index(who)}m{shown}{RESET}" if color else shown


def _label(net: str, buf: str, color: bool) -> str:
    text = f"{net}/{buf}"
    return f"{DIM}{text}{RESET}" if color else text


def _cell(s: str) -> str:
    return s.replace("\t", " ")


def _emit(hits: list[Match], by_path: dict[str, LogFile], args, color: bool) -> None:
    out = sys.stdout
    for m in hits:
        lf = by_path.get(m.path)
        net, buf = (lf.network, lf.buffer) if lf else ("?", os.path.basename(display_path(m.path)))
        ctx = (context_records(m.path, m.line_no, args.context, not args.events)
               if args.context > 0 else [])
        if args.format == "json":
            rec = {
                "timestamp": m.timestamp, "network": net, "buffer": buf, "nick": m.who,
                "message": m.message, "event": m.is_event,
                "path": display_path(m.path), "line": m.line_no,
            }
            if args.context > 0:
                rec["context"] = [
                    {"line": n, "timestamp": ts, "nick": who, "message": msg,
                     "event": ev, "hit": n == m.line_no}
                    for n, ts, who, msg, ev in ctx
                ]
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        elif args.format == "tsv":
            out.write("\t".join(_cell(c) for c in (
                m.timestamp, net, buf, m.who, m.message, display_path(m.path),
                str(m.line_no), "1" if m.is_event else "0",
            )) + "\n")
        else:
            head = [m.timestamp, _label(net, buf, color)]
            nick = _nick(m.who, m.is_event, color)
            out.write("  ".join(head) + "  " + (f"{nick} " if nick else "") + m.message + "\n")
            for n, ts, who, msg, ev in ctx:
                marker = ">>" if n == m.line_no else "  "
                nick = _nick(who, ev, color)
                out.write(f"{marker} {extract_hms(ts)}  " + (f"{nick} " if nick else "") + msg + "\n")
            if ctx:
                out.write("\n")


async def _collect(q: Query, paths: list[str], limit: int) -> list[Match]:
    hits: list[Match] = []
    async for m in run_search(q, paths):
        hits.append(m)
        if limit and len(hits) >= limit:
            break
    return hits


def main(argv: list[str] | None = None) -> int:
    if hasattr(signal, "SIGPIPE"):
        # Behave like grep in a pipeline: die quietly when the reader goes away.
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    ap = build_parser()
    args = ap.parse_args(argv)

    def fail(msg: str) -> int:
        print(f"error: {msg}", file=sys.stderr)
        return 2

    if not args.user and not args.search:
        ap.error("give --search TEXT and/or --user NICK")
    if args.context > 0 and args.format == "tsv":
        ap.error("--context is only available with --format text or json")
    if args.context < 0 or args.limit < 0:
        ap.error("--context and --limit take a non-negative number")

    logs = args.logs
    source = "--logs"
    if logs is None:
        env = os.environ.get("WEELOG_DIR")
        if not env:
            ap.error("no logs directory given. Pass --logs DIR or set the "
                     "WEELOG_DIR environment variable.")
        logs = Path(env)
        source = "$WEELOG_DIR"
    if not logs.exists():
        return fail(f"{logs} (from {source}) does not exist")
    if not logs.is_dir():
        return fail(f"{logs} (from {source}) is not a directory")
    if not shutil.which("rg"):
        return fail("ripgrep (rg) not found on PATH")

    set_write_policy(logs, cache_path().parent, Path("/tmp"))
    try:
        index, _key, _hit = load_index(logs)
    except (OSError, WriteRefused) as e:
        return fail(f"cannot index {logs}: {e}")

    prefix, suffix = read_weechat_nick_wrappers()
    q = Query(
        text=args.search or "", regex=args.regex, case_sensitive=args.case,
        date_from=args.date_from, date_to=args.date_to, nick=" ".join(args.user),
        hide_events=not args.events, include_compressed=args.archives,
        include_system=args.system, nick_wrap_prefix=prefix, nick_wrap_suffix=suffix,
    )
    if args.network:
        q.networks = set(args.network)
    if args.channel:
        wanted = {c.casefold() for c in args.channel}
        q.buffers = {
            (lf.network, lf.buffer) for lf in index
            if lf.buffer.casefold() in wanted and (not q.networks or lf.network in q.networks)
        }
        if not q.buffers:
            return fail("no logs for buffer(s) " + ", ".join(args.channel))
        # Naming a buffer is explicit enough to override the system-buffer filter.
        q.include_system = True

    hits = asyncio.run(_collect(q, select_files(index, q), args.limit))
    hits.sort(key=match_sort_key)
    if hasattr(sys.stdout, "reconfigure"):
        # Log text is UTF-8; a C locale on the other end must not crash the tool.
        sys.stdout.reconfigure(errors="replace")
    _emit(hits, {lf.path: lf for lf in index}, args, _want_color(args.color))
    sys.stdout.flush()
    if args.limit and len(hits) >= args.limit:
        print(f"note: stopped at --limit {args.limit}; pass --limit 0 for all hits",
              file=sys.stderr)
    return 0 if hits else 1
