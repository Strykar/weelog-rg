from __future__ import annotations

import random
import re
from dataclasses import dataclass


RAND_QUERIES = [
    "", "morning", "archived", "channel", "nil",
    "a\tb", "\\d+", "(unterminated", "αβγ", "😀", "a" * 80,
]
RAND_NICKS = ["", "alice", "alice bob", "alice,bob", "UPPER", "__", "x y z", "a" * 100]
# "2026-13-40" is deliberate validator stress, not a typo.
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
    h = hay.casefold()
    pos = 0
    for c in needle.casefold():
        idx = h.find(c, pos)
        if idx < 0:
            return False
        pos = idx + 1
    return True


def patch_debounce_to_immediate(app_module):
    original = app_module.WeelogRg._schedule_search

    def _immediate(self) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer = None
        self._run()

    app_module.WeelogRg._schedule_search = _immediate
    return original


async def check_invariants(app, app_module, last_action: str) -> list[Violation]:
    from textual.widgets import DataTable, Static
    vs: list[Violation] = []
    dt = app.query_one("#results", DataTable)

    if dt.row_count != len(app._matches):
        vs.append(Violation(
            last_action, "rows-match-len",
            f"table {dt.row_count} vs _matches {len(app._matches)}",
        ))

    expected = 3 if app._compact else 5
    if len(dt.columns) != expected:
        vs.append(Violation(
            last_action, "col-count",
            f"table {len(dt.columns)} vs expected {expected}",
        ))

    def _plain(sel: str) -> str:
        r = app.query_one(sel, Static).render()
        return r.plain if hasattr(r, "plain") else str(r)

    if not app._matches and dt.cursor_row is None:
        if "Context - select" not in _plain("#preview-title"):
            vs.append(Violation(last_action, "preview-reset", "stale title"))
        if "(no selection)" not in _plain("#preview-content"):
            vs.append(Violation(last_action, "preview-reset", "stale body"))

    if app.query.hide_events:
        bad = [m for m in app._matches if m.is_event]
        if bad:
            vs.append(Violation(
                last_action, "hide-events", f"{len(bad)} leaked",
            ))

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

    if not app.query.include_compressed and app._matches:
        bad = [m for m in app._matches
               if m.path.endswith(".gz") or m.path.endswith(".zst")]
        if bad:
            vs.append(Violation(
                last_action, "compressed-opt-in",
                f"{len(bad)} compressed paths with include_compressed=False",
            ))

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
    ("f2", "key"),
    ("f3", "key"),
    ("f4", "key"),
    ("Y", "key"),
    ("slash", "key"),
    ("ctrl+l", "key"),
]


async def step(pilot, sel: str, kind: str) -> str:
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
