"""Log-line parsing, timestamps, colour stripping and log-file opening."""
from __future__ import annotations

import gzip
import io
import os
import re
import subprocess
from datetime import date, datetime
from pathlib import Path


# Longer alternatives must come first so they consume their full argument run.
_WEECHAT_COLOR_RE = re.compile(
    r"\x19(?:"
    r"[FB]?\d{2}"
    r"|\*[*!@~/_|]?\d{4,6}"
    r"|\*[FB]?\d{2}"
    r"|@\d{5}"
    r"|![0-9a-fA-F]{6}"
    r")?"
    r"|[\x1a\x1b\x1c]"
)


def strip_weechat_colors(text: str) -> str:
    if not any(b in text for b in "\x19\x1a\x1b\x1c"):
        return text
    return _WEECHAT_COLOR_RE.sub("", text)


# Log text reaches the terminal, so drop any control byte other than tab.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f-\x9f]")


def _display_name(name: str) -> str:
    # File names reach the terminal too, and may not be valid UTF-8.
    name = name.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    return _CONTROL_RE.sub("", name)


def parse_timestamp(ts: str) -> datetime | None:
    # ISO-Z input returns an aware UTC datetime, the classic format a naive one.
    if not ts:
        return None
    s = ts.strip()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def extract_hms(ts: str) -> str:
    dt = parse_timestamp(ts)
    if dt is not None:
        return dt.strftime("%H:%M:%S")
    return ts.replace("T", " ").split(" ", 1)[-1].split(".")[0]


def extract_date(ts: str) -> date | None:
    dt = parse_timestamp(ts)
    return dt.date() if dt is not None else None


class _ProcReader(io.TextIOWrapper):
    def __init__(self, proc: subprocess.Popen):
        super().__init__(proc.stdout, encoding="utf-8", errors="replace")
        self._proc = proc

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._proc.returncode is None:
                try:
                    self._proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait()
            if self._proc.returncode and self._proc.returncode > 0:
                raise OSError(
                    f"zstdcat exited {self._proc.returncode} (corrupt .zst?)"
                )


def open_log(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    if path.endswith(".zst"):
        proc = subprocess.Popen(
            ["zstdcat", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        return _ProcReader(proc)
    return open(path, encoding="utf-8", errors="replace")


def read_weechat_nick_wrappers() -> tuple[str, str]:
    candidates = [
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "weechat" / "logger.conf",
        Path.home() / ".weechat" / "logger.conf",
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        prefix = ""
        suffix = ""
        in_file = False
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("[") and line.endswith("]"):
                in_file = (line == "[file]")
                continue
            if not in_file:
                continue
            for key in ("nick_prefix", "nick_suffix"):
                if line.startswith(f"{key} ="):
                    val = line.split("=", 1)[1].strip()
                    if len(val) >= 2 and val[0] == val[-1] == '"':
                        val = val[1:-1]
                    if key == "nick_prefix":
                        prefix = val
                    else:
                        suffix = val
        return prefix, suffix
    return "", ""


def strip_nick_wrappers(who: str, prefix: str, suffix: str) -> str:
    if prefix and who.startswith(prefix):
        who = who[len(prefix):]
    if suffix and who.endswith(suffix):
        who = who[: -len(suffix)]
    return who


EVENT_PREFIXES = {"▬▬▶", "◀▬▬", "-->", "<--", "--"}


def parse_line(raw: str) -> tuple[str, str, str, bool]:
    parts = _CONTROL_RE.sub("", strip_weechat_colors(raw)).split("\t", 2)
    if len(parts) < 2:
        return "", "", parts[0] if parts else "", False
    while len(parts) < 3:
        parts.append("")
    ts, who, msg = parts
    return ts, who, msg, who in EVENT_PREFIXES


def context_groups(
    path: str, line_nos: list[int], span: int, hide_events: bool,
) -> list[list[tuple[int, str, str, str, bool, bool]]]:
    """Context around several hits in one pass; touching ranges share a group."""
    hits = sorted(set(line_nos))
    if not hits:
        return []
    ranges: list[list[int]] = []
    for n in hits:
        lo, hi = max(1, n - span), n + span
        if ranges and lo <= ranges[-1][1] + 1:
            ranges[-1][1] = max(ranges[-1][1], hi)
        else:
            ranges.append([lo, hi])
    hit_set = set(hits)
    groups: list[list[tuple[int, str, str, str, bool, bool]]] = []
    current: list[tuple[int, str, str, str, bool, bool]] | None = None
    r = 0
    try:
        with open_log(path) as f:
            for i, ln in enumerate(f, 1):
                while r < len(ranges) and i > ranges[r][1]:
                    r += 1
                    current = None
                if r >= len(ranges):
                    break
                if i < ranges[r][0]:
                    continue
                if current is None:
                    current = []
                    groups.append(current)
                ts, who, msg, is_event = parse_line(ln)
                is_hit = i in hit_set
                if hide_events and is_event and not is_hit:
                    continue
                current.append((i, ts, who, msg, is_event, is_hit))
    except (OSError, EOFError, gzip.BadGzipFile):
        return []
    return groups


def context_records(
    path: str, line_no: int, span: int, hide_events: bool,
) -> list[tuple[int, str, str, str, bool]]:
    """Lines around line_no as (line number, timestamp, who, message, is_event)."""
    groups = context_groups(path, [line_no], span, hide_events)
    return [rec[:5] for rec in groups[0]] if groups else []


def context_lines(
    path: str, line_no: int, span: int, hide_events: bool,
) -> list[str]:
    return [
        f"{'>>' if i == line_no else '  '} {ts}\t{who}\t{msg}"
        for i, ts, who, msg, _ in context_records(path, line_no, span, hide_events)
    ]
