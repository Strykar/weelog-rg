"""fzf-style nick subsequence: short input matches longer nicks
('alb' → 'alice_bot'), tab anchors prevent body-mention leaks. Both
properties tested in one fixture so a regression in either fails."""
from __future__ import annotations


async def test_subsequence_match_and_body_anchor(app_module, tmp_path):
    """Three nicks plus a body that mentions one of them by name. The
    subseq filter for 'alb' must match the 'alice_bot' speaker (a-l-b
    in order) but never the body line where bob talks about 'alice_bot'."""
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
    q = app_module.Query(nick="alb")  # subseq of alice_bot, not of others
    matches = [
        m async for m in
        app_module.run_search(q, app_module.select_files(idx, q))
    ]

    whos = {m.who for m in matches}
    assert "alice_bot" in whos
    # Body mention by bob must NOT leak in via 'alice_bot' substring.
    assert "bob" not in whos
    assert "carol" not in whos
