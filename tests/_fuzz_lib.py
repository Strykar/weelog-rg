"""Shared fuzz harness for weelog-hindsight.

Used by both `tests/test_fuzz.py` (pytest wrapper, runs against the
synthetic fixture) and `scripts/fuzz.py` (standalone runner, can target
real logs). Keeping the invariants and action dispatchers here means
the two harnesses can't drift into vacuous-green-light territory.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass


RAND_QUERIES = [
    "", "morning", "archived", "channel", "nil",
    "a\tb", "\\d+", "(unterminated", "αβγ", "😀", "a" * 80,
]
RAND_NICKS = ["", "alice", "alice bob", "alice,bob", "UPPER", "__", "x y z", "a" * 100]
# "2026-13-40" is intentional input-validator stress (out-of-range
# month + day), not a typo.
RAND_DATES = [
    "", "2026-01-01", "2024-05-01", "1970-01-01",
    "not-a-date", "2026-13-40", "2030-01-01",
]


@dataclass
class Violation:
    action: str
    invariant: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.invariant}] after {self.action!r}: {self.detail}"


def _subseq(needle: str, hay: str) -> bool:
    """fzf-style subsequence: every char of `needle`, in order, in `hay`."""
    h = hay.casefold()
    pos = 0
    for c in needle.casefold():
        idx = h.find(c, pos)
        if idx < 0:
            return False
        pos = idx + 1
    return True


def patch_debounce_to_immediate(app_module):
    """Bypass the 300 ms debounce timer entirely: call the search worker
    directly so `wait_for_complete` is all that's needed to drain it.
    Returns the original method so callers can restore it on teardown."""
    original = app_module.Hindsight._schedule_search

    def _immediate(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer = None
        self._run()

    app_module.Hindsight._schedule_search = _immediate
    return original


async def check_invariants(app, app_module, last_action: str) -> list[Violation]:
    from textual.widgets import DataTable, Static
    vs: list[Violation] = []
    dt = app.query_one("#results", DataTable)

    # Row/list length agreement.
    if dt.row_count != len(app._matches):
        vs.append(Violation(
            last_action, "rows-match-len",
            f"table {dt.row_count} vs _matches {len(app._matches)}",
        ))

    # Column count: compact has 3, full has 5.
    expected = 3 if app._compact else 5
    if len(dt.columns) != expected:
        vs.append(Violation(
            last_action, "col-count",
            f"table {len(dt.columns)} vs expected {expected}",
        ))

    # Preview reset when nothing selectable.
    def _plain(sel: str) -> str:
        r = app.query_one(sel, Static).render()
        return r.plain if hasattr(r, "plain") else str(r)

    if not app._matches and dt.cursor_row is None:
        if "Context - select" not in _plain("#preview-title"):
            vs.append(Violation(last_action, "preview-reset", "stale title"))
        if "(no selection)" not in _plain("#preview-content"):
            vs.append(Violation(last_action, "preview-reset", "stale body"))

    # hide_events honoured.
    if app.query.hide_events:
        bad = [m for m in app._matches if m.is_event]
        if bad:
            vs.append(Violation(
                last_action, "hide-events", f"{len(bad)} leaked",
            ))

    # Nick filter is fzf-style subsequence: every result's `who` must
    # be a supermatch of at least one input nick. Exact-match would
    # pass vacuously on any non-literal input (e.g. "alb" → "alice_bot").
    nicks = [n for n in re.split(r"[,\s]+", app.query.nick.strip()) if n]
    if nicks and app._matches:
        bad = [
            m for m in app._matches
            if not any(_subseq(n, m.who) for n in nicks)
        ]
        if bad:
            vs.append(Violation(
                last_action, "nick-filter",
                f"{len(bad)} outside {nicks} (example {bad[0].who!r})",
            ))

    # Date bounds. Use the script's own parser so ISO-Z lines are
    # actually checked, not silently skipped past.
    if app.query.date_from or app.query.date_to:
        bad = []
        for m in app._matches:
            d = app_module.extract_date(m.timestamp)
            if d is None:
                continue
            if app.query.date_from and d < app.query.date_from:
                bad.append(d)
            if app.query.date_to and d > app.query.date_to:
                bad.append(d)
        if bad:
            vs.append(Violation(
                last_action, "date-filter",
                f"{len(bad)} outside "
                f"[{app.query.date_from}, {app.query.date_to}]",
            ))

    # Scope filters.
    if app.query.networks and app._matches:
        by_path = {lf.path: lf for lf in app.index}
        bad = [m for m in app._matches
               if by_path.get(m.path)
               and by_path[m.path].network not in app.query.networks]
        if bad:
            vs.append(Violation(
                last_action, "network-scope", f"{len(bad)} leaked",
            ))
    if app.query.buffers and app._matches:
        by_path = {lf.path: lf for lf in app.index}
        bad = [m for m in app._matches
               if by_path.get(m.path)
               and (by_path[m.path].network, by_path[m.path].buffer)
               not in app.query.buffers]
        if bad:
            vs.append(Violation(
                last_action, "buffer-scope", f"{len(bad)} leaked",
            ))

    # Compressed opt-in.
    if not app.query.include_compressed and app._matches:
        bad = [m for m in app._matches
               if m.path.endswith(".gz") or m.path.endswith(".zst")]
        if bad:
            vs.append(Violation(
                last_action, "compressed-opt-in",
                f"{len(bad)} compressed paths with include_compressed=False",
            ))

    # System-buffer opt-in. select_files gates meta (network starts
    # with "(") and znc/soju/service kinds. Server buffers are always
    # shown regardless of include_system, so don't flag those.
    if not app.query.include_system and app._matches:
        _gated_kinds = {"znc", "soju", "service"}
        by_path = {lf.path: lf for lf in app.index}
        bad = []
        for m in app._matches:
            lf = by_path.get(m.path)
            if not lf:
                continue
            if (lf.network.startswith("(")
                    or app_module.classify_buffer(lf.network, lf.buffer) in _gated_kinds):
                bad.append(m)
        if bad:
            vs.append(Violation(
                last_action, "system-opt-in",
                f"{len(bad)} system-buffer rows with include_system=False "
                f"(example: {bad[0].path})",
            ))

    return vs


async def do_set_input(pilot, selector: str, value: str) -> str:
    from textual.widgets import Input
    inp = pilot.app.query_one(selector, Input)
    inp.value = value
    # Debounce is patched to fire immediately; just give the loop a tick.
    await pilot.pause(0.01)
    return f"set {selector}={value!r}"


async def do_toggle(pilot, selector: str) -> str:
    from textual.widgets import Checkbox
    cb = pilot.app.query_one(selector, Checkbox)
    cb.value = not cb.value
    await pilot.pause(0.01)
    return f"toggle {selector}→{cb.value}"


async def do_click_tree(pilot) -> str:
    from textual.widgets import Tree
    tree = pilot.app.query_one("#tree", Tree)
    tree.root.expand()
    nodes = []

    def walk(n):
        nodes.append(n)
        for c in n.children:
            walk(c)

    walk(tree.root)
    if len(nodes) <= 1:
        return "tree: empty"
    tree.select_node(random.choice(nodes[1:]))
    await pilot.pause(0.01)
    return "tree: select random"


async def do_press(pilot, keys: str) -> str:
    await pilot.press(*keys.split())
    await pilot.pause(0.01)
    return f"press {keys}"


ACTIONS = [
    ("q-text", "input"),
    ("q-nick", "input"),
    ("q-from", "date"),
    ("q-to", "date"),
    ("q-regex", "toggle"),
    ("q-case", "toggle"),
    ("q-events", "toggle"),
    ("q-archives", "toggle"),
    ("q-system", "toggle"),
    ("col-compact", "toggle"),
    ("col-context", "toggle"),
    ("tree", "tree"),
    # Key actions exercised by both harnesses.
    ("f2", "key"),
    ("f3", "key"),
    ("f4", "key"),
    ("Y", "key"),
    ("slash", "key"),
    ("ctrl+l", "key"),
]


async def step(pilot, sel: str, kind: str) -> str:
    """Run one fuzz action by (selector, kind) and return a label."""
    if kind == "input":
        val = random.choice(RAND_QUERIES if "text" in sel else RAND_NICKS)
        return await do_set_input(pilot, f"#{sel}", val)
    if kind == "date":
        return await do_set_input(pilot, f"#{sel}", random.choice(RAND_DATES))
    if kind == "toggle":
        return await do_toggle(pilot, f"#{sel}")
    if kind == "tree":
        return await do_click_tree(pilot)
    if kind == "key":
        return await do_press(pilot, sel)
    raise ValueError(f"unknown action kind: {kind}")
