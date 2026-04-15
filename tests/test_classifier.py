"""classify_buffer: one parametrised table covering every kind the
script recognises. Tests the classifier as a lookup function, which
is all there is to it."""
from __future__ import annotations

import pytest


CASES = [
    # core plugin buffers
    ("(core)",            "chanmon",         "monitor"),
    ("(core)",            "highmon",         "monitor"),
    ("(core)",            "newsmon",         "monitor"),
    ("(core)",            "weechat",         "user_core"),
    ("(core)",            "unknown_thing",   "other"),
    # IRC server buffer (legacy + dated representations)
    ("example-network",   "(server)",        "server"),
    ("example-network",   "example-network", "server"),
    # ZNC: both affix variants
    ("example-network",   "*status",         "znc"),
    ("example-network",   "status*",         "znc"),
    ("example-network",   "*controlpanel",   "znc"),
    # Services (case-insensitive)
    ("example-network",   "ChanServ",        "service"),
    ("example-network",   "nickserv",        "service"),
    ("example-network",   "MemoServ",        "service"),
    # Soju: bouncerserv control buffer (lowercase on disk per
    # logger.file.name_lower_case). Mixed-case input covered by casefold.
    ("example-network",   "bouncerserv",     "soju"),
    ("example-network",   "BouncerServ",     "soju"),
    # Channels
    ("example-network",   "#example",        "channel"),
    ("example-network",   "&local",          "channel"),
    ("example-network",   "+modeless",       "channel"),
    ("example-network",   "!safe-prefix",    "channel"),
    # Plain nicks -> private query
    ("example-network",   "alice",           "pm"),
    ("example-network",   "alice_bot",       "pm"),
]


@pytest.mark.parametrize("network,buffer,expected", CASES)
def test_classify_buffer(app_module, network, buffer, expected):
    assert app_module.classify_buffer(network, buffer) == expected
