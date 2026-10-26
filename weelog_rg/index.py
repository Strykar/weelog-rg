"""Log directory index, buffer classifier, index cache and the write gate."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .parse import _display_name


LEGACY_RE = re.compile(
    r"^(?P<plugin>[^.]+)\.(?P<rest>.+)\.weechatlog(?:\.\d+)?"
    r"(?P<comp>\.gz|\.zst)?$"
)
DATED_RE = re.compile(r"^(?P<buf>.+)\.(?P<md>\d{2})-(?P<md2>\d{2})\.log$")
YEAR_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class LogFile:
    path: str
    network: str
    buffer: str
    day: str | None  # None for legacy single-file buffers
    compressed: bool


def is_soju_buffer(network: str, buffer: str) -> bool:
    del network
    return buffer.casefold() == "bouncerserv"


_SERVICE_NAMES = frozenset({
    "chanserv", "nickserv", "memoserv", "operserv", "botserv",
    "hostserv", "helpserv", "global", "authserv", "saslserv",
    "statserv", "gameserv", "groupserv", "infoserv", "spamserv",
    "rootserv", "alis",
})


def is_service_buffer(buffer: str) -> bool:
    return buffer.casefold() in _SERVICE_NAMES


def is_znc_buffer(buffer: str) -> bool:
    return bool(buffer) and (buffer.startswith("*") or buffer.endswith("*"))


def classify_buffer(network: str, buffer: str) -> str:
    if network == "(core)":
        if buffer in ("chanmon", "highmon", "newsmon"):
            return "monitor"
        if buffer == "weechat":
            return "user_core"
        return "other"
    if buffer == "(server)" or buffer == network:
        return "server"
    if is_znc_buffer(buffer):
        return "znc"
    if is_soju_buffer(network, buffer):
        return "soju"
    if is_service_buffer(buffer):
        return "service"
    if buffer and buffer[0] in "#&+!":
        return "channel"
    return "pm"


def build_index(logs_dir: Path) -> list[LogFile]:
    # Absolute paths can't be mistaken for options by rg, zstdcat or $PAGER.
    logs_dir = logs_dir.absolute()
    out: list[LogFile] = []
    for entry in os.scandir(logs_dir):
        if entry.is_file():
            m = LEGACY_RE.match(entry.name)
            if m:
                plugin = m["plugin"]
                rest = m["rest"]
                if plugin == "irc" and rest.startswith("server."):
                    network = rest[len("server."):]
                    buffer = "(server)"
                elif plugin == "irc" and "." in rest:
                    network, buffer = rest.split(".", 1)
                else:
                    network = f"({plugin})"
                    buffer = rest
                out.append(LogFile(
                    path=entry.path,
                    network=_display_name(network),
                    buffer=_display_name(buffer),
                    day=None,
                    compressed=bool(m["comp"]),
                ))
        elif entry.is_dir() and YEAR_RE.match(entry.name):
            year = entry.name
            for net_entry in os.scandir(entry.path):
                if not net_entry.is_dir():
                    continue
                network = net_entry.name
                for f in os.scandir(net_entry.path):
                    if not f.is_file():
                        continue
                    m = DATED_RE.match(f.name)
                    if not m:
                        continue
                    day = f"{year}-{m['md']}-{m['md2']}"
                    try:
                        date.fromisoformat(day)
                    except ValueError:
                        continue
                    out.append(LogFile(
                        path=f.path,
                        network=_display_name(network),
                        buffer=_display_name(m["buf"]),
                        day=day,
                        compressed=False,
                    ))
    return out


def cache_path() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "weelog-rg" / "index.json"


_ALLOWED_WRITE_ROOTS: list[Path] = []
_LOGS_DIR_RESOLVED: Path | None = None
_EXPORT_NAME_PREFIX = "weelog-rg-"
_EXPORT_SUFFIX = ".tsv"


def set_write_policy(logs_dir: Path, cache_dir: Path, export_dir: Path) -> None:
    global _LOGS_DIR_RESOLVED
    _LOGS_DIR_RESOLVED = logs_dir.resolve()
    _ALLOWED_WRITE_ROOTS.clear()
    _ALLOWED_WRITE_ROOTS.extend([cache_dir.resolve(), export_dir.resolve()])


def _current_allowed_roots() -> list[Path]:
    roots = [cache_path().parent.resolve(), Path("/tmp").resolve()]
    for r in _ALLOWED_WRITE_ROOTS:
        if r not in roots:
            roots.append(r)
    return roots


def open_w(path: Path, exclusive: bool = False, **kwargs):
    assert_writable(path)
    # Exports land in /tmp: O_EXCL refuses a planted file or symlink, 0600 keeps logs private.
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    return os.fdopen(os.open(path, flags, 0o600), "w", **kwargs)


class WriteRefused(PermissionError):
    """Raised by assert_writable; main() turns it into a clean exit."""


def assert_writable(path: Path) -> None:
    """Raise unless path is in the cache or a named /tmp export, and outside --logs."""
    resolved = path.resolve()
    roots = _current_allowed_roots()
    ok = False
    for root in roots:
        try:
            resolved.relative_to(root)
            ok = True
            break
        except ValueError:
            continue
    if not ok:
        raise WriteRefused(
            f"error: refused to write {resolved}. Permitted write roots "
            f"are {[str(r) for r in roots]}. This is a cardinal guard: "
            "the tool never writes outside its cache or explicit export "
            "location."
        )
    if _LOGS_DIR_RESOLVED is not None:
        try:
            resolved.relative_to(_LOGS_DIR_RESOLVED)
            raise WriteRefused(
                f"error: refused to write {resolved} because it sits "
                f"inside --logs ({_LOGS_DIR_RESOLVED}). Logs are "
                "strictly read-only."
            )
        except ValueError:
            pass
    cache_root = cache_path().parent.resolve()
    is_cache = False
    try:
        resolved.relative_to(cache_root)
        is_cache = True
    except ValueError:
        pass
    if not is_cache:
        name = resolved.name
        if not (name.startswith(_EXPORT_NAME_PREFIX) and name.endswith(_EXPORT_SUFFIX)):
            raise WriteRefused(
                f"error: refused to write {resolved}. Export files must "
                f"be named '{_EXPORT_NAME_PREFIX}*{_EXPORT_SUFFIX}'."
            )


def load_index(logs_dir: Path) -> tuple[list[LogFile], str, bool]:
    """Cached entries while the key matches, else a fresh scan. Returns (entries, key, cache_hit)."""
    key = index_key(logs_dir)
    cp = cache_path()
    cache_hit = False
    idx: list[LogFile] | None = None
    if cp.exists():
        try:
            data = json.loads(cp.read_text())
            if data.get("key") == key:
                idx = [LogFile(**e) for e in data["entries"]]
                cache_hit = True
        except (OSError, json.JSONDecodeError, TypeError, KeyError):
            idx = None
    if idx is None:
        idx = build_index(logs_dir)
        cp.parent.mkdir(parents=True, exist_ok=True)
        with open_w(cp, encoding="utf-8") as f:
            json.dump({"key": key, "entries": [asdict(e) for e in idx]}, f)
    return idx, key, cache_hit


def load_or_build_index(logs_dir: Path) -> tuple[list[LogFile], dict]:
    start = time.monotonic()
    idx, _key, cache_hit = load_index(logs_dir)
    total_bytes = 0
    days: list[str] = []
    networks: set[str] = set()
    buffers: set[tuple[str, str]] = set()
    channels: set[tuple[str, str]] = set()
    pms: set[tuple[str, str]] = set()
    kind_counts: dict[str, int] = {}
    for e in idx:
        with contextlib.suppress(OSError):
            total_bytes += os.path.getsize(e.path)
        if e.day:
            days.append(e.day)
        networks.add(e.network)
        buffers.add((e.network, e.buffer))
        kind = classify_buffer(e.network, e.buffer)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if kind == "channel":
            channels.add((e.network, e.buffer))
        elif kind == "pm":
            pms.add((e.network, e.buffer))
    stats = {
        "total": len(idx),
        "compressed": sum(1 for e in idx if e.compressed),
        "legacy": sum(1 for e in idx if e.day is None),
        "bytes": total_bytes,
        "networks": len(networks),
        "buffers": len(buffers),
        "channels": len(channels),
        "pms": len(pms),
        "oldest": min(days) if days else None,
        "newest": max(days) if days else None,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "cache_hit": cache_hit,
        "kinds": kind_counts,
        "logs_dir": str(logs_dir),
    }
    return idx, stats


def index_key(logs_dir: Path) -> str:
    h = hashlib.sha256()
    h.update(b"schema:2\n")
    h.update(os.fsencode(logs_dir.resolve()))
    for entry in sorted(os.scandir(logs_dir), key=lambda e: e.name):
        st = entry.stat(follow_symlinks=False)
        h.update(os.fsencode(entry.name) + f":{st.st_mtime_ns}:{st.st_size}\n".encode())
        if entry.is_dir() and YEAR_RE.match(entry.name):
            for sub in sorted(os.scandir(entry.path), key=lambda e: e.name):
                ss = sub.stat(follow_symlinks=False)
                h.update(b"  " + os.fsencode(sub.name) + f":{ss.st_mtime_ns}:{ss.st_size}\n".encode())
    return h.hexdigest()
