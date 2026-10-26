#!/usr/bin/env python3
"""Render README screenshots of the TUI from the synthetic demo logs.

    .venv/bin/python demo/screenshots.py    # writes demo/results.svg and demo/context.svg
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load(name: str, path: Path):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


async def wait_for_rows(app, pilot, min_rows: int = 1, timeout: float = 8.0) -> int:
    from textual.widgets import DataTable
    table = app.query_one("#results", DataTable)
    waited = 0.0
    while table.row_count < min_rows and waited < timeout:
        await pilot.pause(0.25)
        waited += 0.25
    return table.row_count


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="weelog-demo-"))
    logs = tmp / "logs"
    logs.mkdir()
    os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
    load("weelog_make_logs", REPO / "demo" / "make-logs.py").main(logs)
    tui = load("weelog_rg_script", REPO / "bin" / "weelog-rg")
    tui._set_write_policy(logs, tui.cache_path().parent, Path("/tmp"))
    index, stats = tui.load_or_build_index(logs)
    app = tui.WeelogRg(logs, index, theme="dark", index_stats=stats)
    from textual.widgets import DataTable, Input

    from textual.widgets import Checkbox

    async def search(pilot, text: str, nick: str = "", date_from: str = "") -> int:
        app.query_one("#q-nick", Input).value = nick
        app.query_one("#q-from", Input).value = date_from
        app.query_one("#q-text", Input).value = text
        await pilot.pause(0.5)
        return await wait_for_rows(app, pilot, 3)

    # Results list: context pane off so the table gets the height.
    async with app.run_test(size=(140, 46)) as pilot:
        await pilot.pause(0.5)
        app.query_one("#col-context", Checkbox).value = False
        rows = await search(pilot, "mkinitcpio")
        table = app.query_one("#results", DataTable)
        table.focus()
        table.move_cursor(row=min(3, rows - 1))
        await pilot.pause(0.6)
        (REPO / "demo" / "results.svg").write_text(app.export_screenshot(title="weelog-rg"))
        print("results rows:", rows)

    # Context pane: it is 34 rows tall on a wide screen, so give the table room too.
    app = tui.WeelogRg(logs, index, theme="dark", index_stats=stats)
    async with app.run_test(size=(140, 62)) as pilot:
        await pilot.pause(0.5)
        rows = await search(pilot, "systemd", nick="kestrel", date_from="2026-06-01")
        table = app.query_one("#results", DataTable)
        table.focus()
        table.move_cursor(row=min(2, rows - 1))
        await pilot.pause(0.6)
        (REPO / "demo" / "context.svg").write_text(app.export_screenshot(title="weelog-rg"))
        print("context rows:", rows)
    for name in ("results.svg", "context.svg"):
        p = REPO / "demo" / name
        print(f"{p.relative_to(REPO)}: {p.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    asyncio.run(main())
