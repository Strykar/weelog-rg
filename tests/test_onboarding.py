from __future__ import annotations


async def test_onboarding_renders_in_preview(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
):
    monkeypatch.setenv("XDG_CACHE_HOME",
                       str(tmp_path_factory.mktemp("cache-outside-logs")))
    from textual.widgets import RichLog, Static
    index, stats = app_module.load_or_build_index(synthetic_logs)
    app = app_module.WeelogRg(synthetic_logs, index, theme="dark",
                               index_stats=stats)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.3)
        preview_title = app.query_one("#preview-title", Static)
        pt = preview_title.render()
        pt_text = pt.plain if hasattr(pt, "plain") else str(pt)
        assert "Welcome" not in pt_text
        assert "/" in pt_text, f"expected a path, got: {pt_text!r}"

        preview = app.query_one("#preview-content", RichLog)
        body_text = "\n".join(str(line) for line in preview.lines)
        assert "log files" in body_text
        assert "Index" in body_text and "ms" in body_text

        results_title = app.query_one("#results-title", Static)
        rt = results_title.render()
        rt_text = rt.plain if hasattr(rt, "plain") else str(rt)
        assert rt_text.strip() == "Results"
