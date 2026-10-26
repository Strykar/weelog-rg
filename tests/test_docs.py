"""The guide, --help and the in-app help must describe what the app actually binds."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUIDE = (REPO / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")

# Textual key name -> how the docs spell it. A new binding must be added here too.
KEY_LABELS = {
    "ctrl+p": "Ctrl+P", "slash": "/", "ctrl+l": "Ctrl+L",
    "f2": "F2", "f3": "F3", "f4": "F4", "enter": "Enter",
    "y": "y", "Y": "Y", "ctrl+e": "Ctrl+E", "question_mark": "?", "ctrl+q": "Ctrl+Q",
}


def _bound_keys(app_module) -> list[str]:
    return [KEY_LABELS[b.key] for b in app_module.WeelogRg.BINDINGS]


def _guide_section(title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", GUIDE, re.S | re.M)
    assert m, f"USER_GUIDE.md has no '## {title}' section"
    return m.group(1)


def test_guide_key_table_lists_every_binding(app_module):
    documented = set(re.findall(r"^\| `([^`]+)`", _guide_section("Key bindings"), re.M))
    for label in _bound_keys(app_module):
        assert label in documented, f"{label!r} is bound but missing from the key table"


def test_help_epilog_lists_every_binding(app_module):
    for label in _bound_keys(app_module):
        assert label in app_module.HELP_EPILOG, f"{label!r} missing from --help"


def test_help_screen_lists_every_binding(app_module):
    for label in _bound_keys(app_module):
        assert label in app_module.HELP_SCREEN_TEXT, f"{label!r} missing from ? screen"


async def test_guide_and_help_screen_describe_exactly_the_chips(
    app_module, synthetic_logs, tmp_path_factory, monkeypatch,
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    idx, stats = app_module.load_or_build_index(synthetic_logs)
    app = app_module.WeelogRg(synthetic_logs, idx, theme="dark", index_stats=stats)
    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)
        chips = {str(c.label) for c in app.screen.query(app_module.Chip)}
    documented = set(re.findall(r"^- \*\*(.+?)\*\*", _guide_section("What each chip does"), re.M))
    assert documented == chips
    for chip in chips:
        assert f"[b]{chip}[/b]" in app_module.HELP_SCREEN_TEXT, f"{chip!r} missing from ? screen"


def test_readme_documents_the_quit_key():
    assert "Ctrl+Q" in README
