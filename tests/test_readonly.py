from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _snapshot(root: Path) -> dict[str, tuple[str, int, int]]:
    # No mtimes: reads can touch atime on some filesystems.
    out: dict[str, tuple[str, int, int]] = {}
    for base, _dirs, files in os.walk(root):
        for fname in files:
            p = Path(base) / fname
            st = p.stat()
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            rel = str(p.relative_to(root))
            out[rel] = (h.hexdigest(), st.st_size, st.st_mode)
    return out


async def _exercise(app_module, logs_dir: Path):
    from textual.widgets import Checkbox, DataTable, Input, Tree

    index, stats = app_module.load_or_build_index(logs_dir)
    app = app_module.WeelogRg(logs_dir, index, theme="dark", index_stats=stats)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)

        app.query_one("#q-text", Input).value = "morning"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        app.query_one("#q-archives", Checkbox).value = True
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        app.query_one("#q-text", Input).value = "archived"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        dt = app.query_one("#results", DataTable)
        if dt.row_count:
            dt.action_cursor_down()
            await pilot.pause(0.2)
        app.query_one("#q-text", Input).value = "morning"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        export_before = set(Path("/tmp").glob("weelog-rg-*.tsv"))
        assert app.query_one("#results", DataTable).row_count > 0, (
            "search for 'morning' should yield results"
        )
        await app.run_action("export")
        await pilot.pause(0.2)
        await pilot.press("enter")
        await pilot.pause(0.4)
        export_after = set(Path("/tmp").glob("weelog-rg-*.tsv"))
        new_exports = export_after - export_before
        assert new_exports, "export action should have written a .tsv file"
        for f in new_exports:
            assert f.stat().st_size > 0, f"export file {f} is empty"
        tree = app.query_one("#tree", Tree)
        tree.root.expand()
        if tree.root.children:
            tree.select_node(tree.root.children[0])
            await app.workers.wait_for_complete()


async def test_logs_dir_unchanged_after_session(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
    debounce_immediate,
):
    cache_dir = tmp_path_factory.mktemp("cache-outside-logs")
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_dir))

    before = _snapshot(synthetic_logs)
    await _exercise(app_module, synthetic_logs)
    after = _snapshot(synthetic_logs)

    added = set(after) - set(before)
    removed = set(before) - set(after)
    assert not added, f"files created in logs dir during session: {added}"
    assert not removed, f"files removed from logs dir during session: {removed}"

    diffs = [
        f"{k}: content/size/mode changed"
        for k in before if before[k] != after[k]
    ]
    assert not diffs, "\n".join(diffs)


def test_startup_guard_rejects_cache_inside_logs(
    app_module, synthetic_logs, monkeypatch
):
    import subprocess
    import sys as _sys

    bad_cache = synthetic_logs / "oops-cache"
    bad_cache.mkdir()
    env = {**os.environ, "XDG_CACHE_HOME": str(bad_cache)}
    script = Path(app_module.__file__)
    proc = subprocess.run(
        [_sys.executable, str(script), "--logs", str(synthetic_logs)],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    assert proc.returncode != 0
    assert "inside the logs" in (proc.stdout + proc.stderr).lower(), (
        f"unexpected error output: {proc.stdout!r} / {proc.stderr!r}"
    )
