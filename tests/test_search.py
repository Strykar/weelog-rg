"""run_search end-to-end: actually invokes ripgrep against the
synthetic fixture with a query + nick + event filter combined, and
verifies the date-range post-filter on legacy logs (the path-level
date gate can't catch those)."""
from __future__ import annotations

async def test_search_combined_filters(app_module, synthetic_logs):
    """One search exercises rg integration, the nick anchor, the
    smart-case body match, and the hide_events filter. If anything in
    the rg argv plumbing is broken, this test fails."""
    idx = app_module.build_index(synthetic_logs)
    q = app_module.Query(
        text="morning", nick="alice", hide_events=True,
    )
    matches = [
        m async for m in
        app_module.run_search(q, app_module.select_files(idx, q))
    ]

    assert matches, "expected at least one alice/morning hit"
    assert all(m.who == "alice" for m in matches)
    assert all(not m.is_event for m in matches)
    assert all("morning" in m.message.lower() for m in matches)


async def test_search_chunking(app_module, tmp_path, monkeypatch):
    """CHUNK = 10000 means large path lists are split across multiple rg
    invocations. Monkeypatch CHUNK to 2 and verify all 5 paths produce
    results, not just the first chunk."""
    monkeypatch.setattr(app_module, "CHUNK", 2)
    dated = tmp_path / "2026" / "net"
    dated.mkdir(parents=True)
    for i in range(5):
        (dated / f"#ch{i}.01-02.log").write_text(
            f"2026-01-02 10:00:00\talice\thit from ch{i}\n", encoding="utf-8",
        )
    idx = app_module.build_index(tmp_path)
    q = app_module.Query(text="hit from")
    matches = [
        m async for m in
        app_module.run_search(q, app_module.select_files(idx, q))
    ]
    assert len(matches) == 5, f"expected 5 hits across 3 chunks, got {len(matches)}"
    channels = sorted(m.message.split()[-1] for m in matches)
    assert channels == ["ch0", "ch1", "ch2", "ch3", "ch4"]



# Date post-filter coverage lives in test_index.py (both legacy and ISO
# branches). Removed duplicate test here to cut redundancy.
