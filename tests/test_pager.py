from __future__ import annotations


async def test_enter_on_result_opens_pager(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch, debounce_immediate,
):
    monkeypatch.setenv("XDG_CACHE_HOME",
                       str(tmp_path_factory.mktemp("cache-outside-logs")))
    calls: list[int] = []
    monkeypatch.setattr(app_module.Hindsight, "action_open_pager",
                        lambda self: calls.append(1))

    from textual.widgets import DataTable, Input
    index, stats = app_module.load_or_build_index(synthetic_logs)
    app = app_module.Hindsight(synthetic_logs, index, theme="dark",
                               index_stats=stats)
    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.pause(0.2)
        app.query_one("#q-text", Input).value = "morning"
        await pilot.pause(0.05)
        await app.workers.wait_for_complete()
        await pilot.pause(0.2)
        app.query_one("#results", DataTable).focus()
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert calls == [1]
