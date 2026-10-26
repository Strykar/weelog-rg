"""Query parameters and file selection."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .index import LogFile, classify_buffer


@dataclass
class Query:
    text: str = ""
    regex: bool = False
    case_sensitive: bool = False
    networks: set[str] = field(default_factory=set)
    buffers: set[tuple[str, str]] = field(default_factory=set)
    date_from: date | None = None
    date_to: date | None = None
    nick: str = ""
    hide_events: bool = True
    include_compressed: bool = False
    include_system: bool = False
    nick_wrap_prefix: str = ""
    nick_wrap_suffix: str = ""


def select_files(index: list[LogFile], q: Query) -> list[str]:
    out: list[str] = []
    for lf in index:
        if lf.compressed and not q.include_compressed:
            continue
        if lf.network.startswith("(") and not q.include_system:
            continue
        kind = classify_buffer(lf.network, lf.buffer)
        if kind in ("znc", "soju", "service") and not q.include_system:
            continue
        if q.networks and lf.network not in q.networks:
            continue
        if q.buffers and (lf.network, lf.buffer) not in q.buffers:
            continue
        if lf.day is not None:
            d = date.fromisoformat(lf.day)
            if q.date_from and d < q.date_from:
                continue
            if q.date_to and d > q.date_to:
                continue
        out.append(lf.path)
    return out


def parse_date(s: str) -> date | None:
    s = s.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None
