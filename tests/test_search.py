from __future__ import annotations

async def test_search_combined_filters(app_module, synthetic_logs):
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
