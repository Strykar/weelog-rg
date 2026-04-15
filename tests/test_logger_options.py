"""Coverage for the user-configurable WeeChat logger options we
accommodate: timestamp formats, colour-line escapes, nick wrappers.
One end-to-end test that exercises all three at once, plus a focused
regex test since the colour-stripping pattern is non-trivial."""
from __future__ import annotations


async def test_end_to_end_with_all_logger_options_configured(
    app_module, tmp_path, monkeypatch,
):
    """Build a fixture whose lines exercise every quirk at once:
    ISO-8601 timestamps, colour escapes in the message, and wrapped
    nicks. Configure logger.conf so the wrappers are known. Search
    for the bare nick and assert that:
      - the search matched (timestamp parsed, regex built correctly)
      - the displayed who is unwrapped
      - the message has colour escapes stripped
    """
    # Point weechat config discovery at a tmp dir with our prefix/suffix.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    cfg = tmp_path / "config" / "weechat" / "logger.conf"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[file]\nnick_prefix = "|"\nnick_suffix = "|"\n',
                   encoding="utf-8")
    prefix, suffix = app_module.read_weechat_nick_wrappers()
    assert (prefix, suffix) == ("|", "|")

    # Fixture: dated layout, ISO timestamp, colour codes in message.
    logs = tmp_path / "logs"
    dated = logs / "2026" / "example-network"
    dated.mkdir(parents=True)
    (dated / "#chan.01-02.log").write_text(
        "2026-01-02T10:00:00.123Z\t|alice|\t\x1908hello \x19F12there\x1c\n"
        "2026-01-02T10:00:10.456Z\t|bob|\treply\n",
        encoding="utf-8",
    )

    idx = app_module.build_index(logs)
    q = app_module.Query(
        nick="alice",
        nick_wrap_prefix=prefix,
        nick_wrap_suffix=suffix,
    )
    matches = [
        m async for m in
        app_module.run_search(q, app_module.select_files(idx, q))
    ]

    assert matches, "wrapped nick with ISO timestamp must be findable"
    m = matches[0]
    # Nick is unwrapped for display.
    assert m.who == "alice"
    # Colour escapes stripped from the body.
    assert "\x19" not in m.message
    assert "\x1c" not in m.message
    assert "hello" in m.message and "there" in m.message
    # ISO timestamp parses for the relative/ago column.
    assert app_module.parse_timestamp(m.timestamp) is not None
    assert app_module.extract_date(m.timestamp).isoformat() == "2026-01-02"


def test_strip_weechat_colors_regex(app_module):
    """The regex has a few branches (FNN, BNN, *..., @..., !...) that
    each need to consume their argument bytes. One test with every
    branch + a stray intro byte confirms the regex isn't eating
    visible text."""
    raw = (
        "\x1908a"              # plain NN arg, then 'a'
        "\x19F12b"             # foreground FNN, then 'b'
        "\x19B34c"             # background BNN, then 'c'
        "\x19*F12d"            # combined *FNN, then 'd'
        "\x19@12345e"          # terminal 256 @NNNNN, then 'e'
        # 24-bit: !+6 hex must consume exactly six bytes. Trailing 'z'
        # (non-hex) makes the boundary unambiguous: a hex trailer would
        # read as either 6-or-7 consumed.
        "\x19!abcdefz"
        "\x19g"                # stray intro: only the intro is stripped
        "\x1ah"                # attribute set
        "\x1ci"                # reset
        "\x1bj"                # bare attribute byte (was missing from
                               # the fast-path guard before the fix)
    )
    out = app_module.strip_weechat_colors(raw)
    assert out == "abcdezghij", f"unexpected: {out!r}"
