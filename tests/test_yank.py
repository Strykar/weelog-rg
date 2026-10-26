from __future__ import annotations


def _patch_clipboard(app, calls: list):
    app.copy_to_clipboard = lambda text: calls.append(text)


async def test_yank_deny_keeps_clipboard_empty(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
):
    monkeypatch.setenv("XDG_CACHE_HOME",
                       str(tmp_path_factory.mktemp("cache-outside-logs")))
    calls: list[str] = []

    from textual.widgets import DataTable, Input
    index, stats = app_module.load_or_build_index(synthetic_logs)
    app = app_module.WeelogRg(synthetic_logs, index, theme="dark",
                               index_stats=stats)
    _patch_clipboard(app, calls)
    async with app.run_test(size=(180, 50)) as pilot:
        await pilot.pause(0.2)
        app.query_one("#q-text", Input).value = "morning"
        await pilot.pause(0.5)
        assert app.query_one("#results", DataTable).row_count > 0

        await app.run_action("yank")
        await pilot.pause(0.2)
        await pilot.press("n")
        await pilot.pause(0.2)
        assert calls == [], "clipboard written despite consent denial"
        assert not app._clipboard_consent


async def test_yank_accept_then_cursor(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
):
    monkeypatch.setenv("XDG_CACHE_HOME",
                       str(tmp_path_factory.mktemp("cache-outside-logs")))
    calls: list[str] = []

    from textual.widgets import DataTable, Input
    index, stats = app_module.load_or_build_index(synthetic_logs)
    app = app_module.WeelogRg(synthetic_logs, index, theme="dark",
                               index_stats=stats)
    _patch_clipboard(app, calls)
    async with app.run_test(size=(180, 50)) as pilot:
        await pilot.pause(0.2)
        app.query_one("#q-text", Input).value = "morning"
        await pilot.pause(0.5)
        dt = app.query_one("#results", DataTable)
        assert dt.row_count >= 2

        await app.run_action("yank")
        await pilot.pause(0.2)
        await pilot.press("y")
        await pilot.pause(0.2)
        assert len(calls) == 1, "consent accept should re-invoke yank"

        calls.clear()
        dt.action_cursor_down()
        await pilot.pause(0.1)
        assert dt.cursor_row == 1

        await app.run_action("yank")
        await pilot.pause(0.1)

        assert len(calls) == 1
        payload = calls[0]
        target = app._matches[dt.cursor_row]
        assert target.who in payload
        assert payload.startswith(target.timestamp)


async def test_yank_context_copies_window(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
):
    monkeypatch.setenv("XDG_CACHE_HOME",
                       str(tmp_path_factory.mktemp("cache-outside-logs")))
    calls: list[str] = []

    from textual.widgets import Input
    index, stats = app_module.load_or_build_index(synthetic_logs)
    app = app_module.WeelogRg(synthetic_logs, index, theme="dark",
                               index_stats=stats)
    _patch_clipboard(app, calls)
    async with app.run_test(size=(180, 50)) as pilot:
        await pilot.pause(0.2)
        app.query_one("#q-text", Input).value = "morning"
        await pilot.pause(0.5)
        app._clipboard_consent = True
        app.set_focus(None)
        await app.run_action("yank_context")
        await pilot.pause(0.1)
        assert len(calls) == 1
        assert ">>" in calls[0]
