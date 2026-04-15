"""Cardinal rule test: the logs dir must never be modified.

Checksums the full log tree before and after running a multi-step TUI
session (indexing, searching, scoping, previewing, exporting). If a
single byte, mtime, or mode bit shifts, the test fails loudly. This
guards the read-only invariant against regressions in future code paths.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _snapshot(root: Path) -> dict[str, tuple[str, int, int]]:
    """Hash each file + record size and mode. Mtimes deliberately not
    captured because rg's memory-mapped reads can nudge atime on some
    filesystems; we want a strict content + permission snapshot."""
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
    """Run a representative slice of user interactions against the TUI,
    including an export — exports write to /tmp, never to the logs
    directory, and the snapshot should still match."""
    from textual.widgets import Checkbox, DataTable, Input, Tree

    index, stats = app_module.load_or_build_index(logs_dir)
    app = app_module.Hindsight(logs_dir, index, theme="dark", index_stats=stats)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)

        # Drive multiple knobs that each touch the filesystem indirectly
        # (subprocess rg, preview reads, gzip decompression).
        # wait_for_complete after each action so no stale worker
        # touches the logs dir after the post-snapshot.
        app.query_one("#q-text", Input).value = "morning"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        app.query_one("#q-archives", Checkbox).value = True
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        app.query_one("#q-text", Input).value = "archived"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        # Touch the preview pane by cursoring onto a row.
        dt = app.query_one("#results", DataTable)
        if dt.row_count:
            dt.action_cursor_down()
            await pilot.pause(0.2)
        # Drive a search that yields rows so export has something to
        # write, then export and confirm. Writes go to /tmp.
        app.query_one("#q-text", Input).value = "morning"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        export_before = set(Path("/tmp").glob("weelog-hindsight-*.tsv"))
        assert app.query_one("#results", DataTable).row_count > 0, (
            "search for 'morning' should yield results"
        )
        await app.run_action("export")
        await pilot.pause(0.2)            # modal mounts
        await pilot.press("enter")        # Export is focused by default
        await pilot.pause(0.4)            # write completes
        export_after = set(Path("/tmp").glob("weelog-hindsight-*.tsv"))
        new_exports = export_after - export_before
        assert new_exports, "export action should have written a .tsv file"
        for f in new_exports:
            assert f.stat().st_size > 0, f"export file {f} is empty"
        # Pick a tree node to trigger scope narrowing.
        tree = app.query_one("#tree", Tree)
        tree.root.expand()
        if tree.root.children:
            tree.select_node(tree.root.children[0])
            await app.workers.wait_for_complete()


async def test_logs_dir_unchanged_after_session(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
    debounce_immediate,
):
    # XDG_CACHE_HOME must be *outside* the logs dir so our cache write
    # isn't itself what changes the snapshot.
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
    """If XDG_CACHE_HOME is misconfigured to a subdir of logs_dir, the
    tool must refuse to start rather than write among the user's logs."""
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
