from __future__ import annotations

import asyncio
from pathlib import Path


def _build_mixed_fixture(root: Path) -> None:
    dated = root / "2026" / "beta-network"
    dated.mkdir(parents=True)
    (dated / "#zebra.03-15.log").write_text(
        "2026-03-15 10:00:00\talice\trecent\n", encoding="utf-8",
    )
    (dated / "#alpha.01-01.log").write_text(
        "2026-01-01 10:00:00\tbob\told\n", encoding="utf-8",
    )
    dated2 = root / "2026" / "alpha-network"
    dated2.mkdir(parents=True)
    (dated2 / "#chan.01-02.log").write_text(
        "2026-01-02 10:00:00\tcarol\thello\n", encoding="utf-8",
    )


def test_tree_sorts_alphabetically(
    app_module, tmp_path, tmp_path_factory, monkeypatch,
):
    monkeypatch.setenv("XDG_CACHE_HOME",
                       str(tmp_path_factory.mktemp("cache-outside-logs")))
    _build_mixed_fixture(tmp_path)

    async def run():
        from textual.widgets import Tree
        idx, stats = app_module.load_or_build_index(tmp_path)
        app = app_module.Hindsight(tmp_path, idx, theme="dark",
                                   index_stats=stats)
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause(0.3)
            tree = app.query_one("#tree", Tree)
            net_labels = [str(n.label) for n in tree.root.children]
            assert net_labels[0].startswith("alpha-network"), (
                f"expected alpha-network first (alphabetical), got: {net_labels}"
            )
            for net_node in tree.root.children:
                if "beta-network" in str(net_node.label):
                    buf_labels = [str(c.label) for c in net_node.children]
                    assert buf_labels[0].startswith("#alpha"), (
                        f"expected #alpha first within beta-network, got: {buf_labels}"
                    )
                    break

    asyncio.run(run())
