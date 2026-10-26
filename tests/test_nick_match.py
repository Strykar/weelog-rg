from __future__ import annotations


async def test_subsequence_match_and_body_anchor(app_module, tmp_path):
    dated = tmp_path / "2026" / "example-network"
    dated.mkdir(parents=True)
    (dated / "#chan.01-02.log").write_text(
        "2026-01-02 10:00:00\talice\thello\n"
        "2026-01-02 10:00:10\talice_bot\tautomated\n"
        "2026-01-02 10:00:20\tbob\treplying about alice_bot in the body\n"
        "2026-01-02 10:00:30\tcarol\tunrelated\n",
        encoding="utf-8",
    )
    idx = app_module.build_index(tmp_path)
    q = app_module.Query(nick="alb")
    matches = [
        m async for m in
        app_module.run_search(q, app_module.select_files(idx, q))
    ]

    whos = {m.who for m in matches}
    assert "alice_bot" in whos
    assert "bob" not in whos
    assert "carol" not in whos
