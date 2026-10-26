from __future__ import annotations


async def test_end_to_end_with_all_logger_options_configured(
    app_module, tmp_path, monkeypatch,
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    cfg = tmp_path / "config" / "weechat" / "logger.conf"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[file]\nnick_prefix = "|"\nnick_suffix = "|"\n',
                   encoding="utf-8")
    prefix, suffix = app_module.read_weechat_nick_wrappers()
    assert (prefix, suffix) == ("|", "|")

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
    assert m.who == "alice"
    assert "\x19" not in m.message
    assert "\x1c" not in m.message
    assert "hello" in m.message and "there" in m.message
    assert app_module.parse_timestamp(m.timestamp) is not None
    assert app_module.extract_date(m.timestamp).isoformat() == "2026-01-02"


def test_strip_weechat_colors_regex(app_module):
    raw = (
        "\x1908a"
        "\x19F12b"
        "\x19B34c"
        "\x19*F12d"
        "\x19@12345e"
        "\x19!abcdefz"        # non-hex z pins the six-byte boundary
        "\x19g"
        "\x1ah"
        "\x1ci"
        "\x1bj"
    )
    out = app_module.strip_weechat_colors(raw)
    assert out == "abcdezghij", f"unexpected: {out!r}"
