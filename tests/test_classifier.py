from __future__ import annotations

import pytest


CASES = [
    ("(core)",            "chanmon",         "monitor"),
    ("(core)",            "highmon",         "monitor"),
    ("(core)",            "newsmon",         "monitor"),
    ("(core)",            "weechat",         "user_core"),
    ("(core)",            "unknown_thing",   "other"),
    ("example-network",   "(server)",        "server"),
    ("example-network",   "example-network", "server"),
    ("example-network",   "*status",         "znc"),
    ("example-network",   "status*",         "znc"),
    ("example-network",   "*controlpanel",   "znc"),
    ("example-network",   "ChanServ",        "service"),
    ("example-network",   "nickserv",        "service"),
    ("example-network",   "MemoServ",        "service"),
    ("example-network",   "bouncerserv",     "soju"),
    ("example-network",   "BouncerServ",     "soju"),
    ("example-network",   "#example",        "channel"),
    ("example-network",   "&local",          "channel"),
    ("example-network",   "+modeless",       "channel"),
    ("example-network",   "!safe-prefix",    "channel"),
    ("example-network",   "alice",           "pm"),
    ("example-network",   "alice_bot",       "pm"),
]


@pytest.mark.parametrize("network,buffer,expected", CASES)
def test_classify_buffer(app_module, network, buffer, expected):
    assert app_module.classify_buffer(network, buffer) == expected
