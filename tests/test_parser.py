from __future__ import annotations

import pytest


def test_chat_line(app_module):
    ts, who, msg, is_event = app_module.parse_line(
        "2026-01-02 10:00:30\talice\tgood morning\n"
    )
    assert (ts, who, msg, is_event) == (
        "2026-01-02 10:00:30", "alice", "good morning", False,
    )


@pytest.mark.parametrize("glyph", ["▬▬▶", "◀▬▬", "-->", "<--", "--"])
def test_event_prefix_recognised(app_module, glyph):
    _, who, msg, is_event = app_module.parse_line(
        f"2026-01-02 10:00:00\t{glyph}\tjoined\twith\textra\ttabs\n"
    )
    assert who == glyph
    assert is_event is True
    assert msg == "joined\twith\textra\ttabs"
