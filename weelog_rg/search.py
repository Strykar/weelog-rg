"""Run ripgrep over the selected files and turn its JSON output into matches."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime

from .parse import extract_date, parse_line, parse_timestamp, strip_nick_wrappers
from .query import Query


@dataclass
class Match:
    path: str
    line_no: int
    timestamp: str
    who: str  # nick, or an event glyph such as "-->"
    message: str
    is_event: bool


def match_sort_key(m: Match) -> tuple:
    dt = parse_timestamp(m.timestamp) or datetime.min
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return (dt, m.path, m.line_no)


def _rg_text(obj: dict) -> str:
    # rg emits base64 "bytes" instead of "text" when the value is not valid UTF-8.
    if "text" in obj:
        return obj["text"]
    return os.fsdecode(base64.b64decode(obj["bytes"]))


# Bounds the per-nick subsequence regex.
NICK_INPUT_MAX = 32
CHUNK = 10000


def rg_args(q: Query) -> list[str] | None:
    """Build the rg argv for a query, or None when there is nothing to search."""
    pattern = q.text
    args = ["rg", "--json", "-z", "--no-messages", "-C", "0"]
    if not q.case_sensitive:
        args.append("-i")
    nicks = [
        n[:NICK_INPUT_MAX]
        for n in re.split(r"[,\s]+", q.nick.strip())
        if n
    ]
    regex_mode = q.regex or bool(nicks)
    if nicks:
        def _subseq(nick: str) -> str:
            chars = [re.escape(c) for c in nick]
            return "[^\\t]*" + "[^\\t]*".join(chars) + "[^\\t]*"

        nick_alt = "|".join(_subseq(n) for n in nicks)
        wp = re.escape(q.nick_wrap_prefix)
        ws = re.escape(q.nick_wrap_suffix)
        anchor = rf"\t{wp}({nick_alt}){ws}\t"
        if pattern:
            body = pattern if q.regex else re.escape(pattern)
            pattern = rf"{anchor}.*{body}"
        else:
            pattern = anchor
    elif not pattern:
        return None
    if regex_mode:
        args += ["-e", pattern]
    else:
        args += ["-F", "-e", pattern]
    return args


def match_from_rg(obj: dict, q: Query) -> Match | None:
    """Turn one rg --json record into a Match, or None when it is not a wanted hit."""
    if obj.get("type") != "match":
        return None
    data = obj["data"]
    path = _rg_text(data["path"])
    line_no = data["line_number"]
    raw = data["lines"].get("text") or ""
    ts, who, msg, is_event = parse_line(raw)
    if q.hide_events and is_event:
        return None
    # Legacy logs span all dates. Unparseable timestamps are kept.
    if q.date_from or q.date_to:
        d = extract_date(ts)
        if d is not None and q.date_from and d < q.date_from:
            return None
        if d is not None and q.date_to and d > q.date_to:
            return None
    if q.nick_wrap_prefix or q.nick_wrap_suffix:
        who = strip_nick_wrappers(who, q.nick_wrap_prefix, q.nick_wrap_suffix)
    return Match(path, line_no, ts, who, msg, is_event)


async def run_search(q: Query, paths: list[str]):
    if not paths:
        return
    args = rg_args(q)
    if args is None:
        return
    # rg has no --files-from, so chunk paths to stay under ARG_MAX.
    for i in range(0, len(paths), CHUNK):
        chunk = paths[i:i + CHUNK]
        proc = await asyncio.create_subprocess_exec(
            *args, *chunk,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdout
        try:
            async for line in proc.stdout:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                m = match_from_rg(obj, q)
                if m is not None:
                    yield m
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 1.0)
                except TimeoutError:
                    proc.kill()
