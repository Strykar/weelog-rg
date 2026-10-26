from __future__ import annotations

from pathlib import Path


def _build_big_fixture(root: Path, n_lines: int = 600) -> None:
    big_dir = root / "2026" / "example-network"
    big_dir.mkdir(parents=True)
    lines = "".join(
        f"2026-01-{(i % 28) + 1:02d} 10:00:00\talice\thit number {i}\n"
        for i in range(n_lines)
    )
    (big_dir / "#big.01-02.log").write_text(lines, encoding="utf-8")


async def test_500_cap_surfaces_truncated_marker(
    app_module, tmp_path, tmp_path_factory, monkeypatch, debounce_immediate,
):
    monkeypatch.setenv("XDG_CACHE_HOME",
                       str(tmp_path_factory.mktemp("cache-outside-logs")))
    _build_big_fixture(tmp_path, n_lines=600)

    from textual.widgets import DataTable, Input, Static
    idx, stats = app_module.load_or_build_index(tmp_path)
    app = app_module.WeelogRg(tmp_path, idx, theme="dark", index_stats=stats)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)
        app.query_one("#q-text", Input).value = "hit"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        await pilot.pause(0.1)
        dt = app.query_one("#results", DataTable)
        assert dt.row_count == 500, (
            f"expected the cap to clamp at 500, got {dt.row_count}"
        )
        title_widget = app.query_one("#results-title", Static)
        title = title_widget.render()
        title = title.plain if hasattr(title, "plain") else str(title)
        assert "500+" in title and "truncated" in title, (
            f"truncation not surfaced in title: {title!r}"
        )
