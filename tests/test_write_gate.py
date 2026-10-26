from __future__ import annotations

from pathlib import Path

import pytest


def _allowed_cache(_app, tmp_path, _logs):
    target = tmp_path / "weelog-hindsight" / "index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target

def _allowed_export(_app, _tmp, _logs):
    return Path("/tmp") / "weelog-hindsight-20260101-120000.tsv"

def _refused_random(_app, _tmp, _logs):
    return Path("/etc/passwd")

def _refused_export_wrong_prefix(_app, _tmp, _logs):
    return Path("/tmp/passwd")

def _refused_export_wrong_suffix(_app, _tmp, _logs):
    return Path("/tmp/weelog-hindsight-x.exe")

def _refused_outside_via_traversal(_app, _tmp, _logs):
    return Path("/tmp/../etc/weelog-hindsight-x.tsv")

def _refused_symlink_to_logs(_app, tmp_path, _logs):
    logs_dir = tmp_path / "fake-logs"
    logs_dir.mkdir()
    link = tmp_path / "weelog-hindsight" / "sneaky.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(logs_dir / "index.json")
    _app._set_write_policy(logs_dir, tmp_path / "weelog-hindsight", Path("/tmp"))
    return link


CASES = [
    ("allowed:cache",            _allowed_cache,                True,  None),
    ("allowed:export",           _allowed_export,               True,  None),
    ("refused:outside",          _refused_random,               False, "refused to write"),
    ("refused:wrong-prefix",     _refused_export_wrong_prefix,  False, "Export files must"),
    ("refused:wrong-suffix",     _refused_export_wrong_suffix,  False, "Export files must"),
    ("refused:outside-via-dotdot", _refused_outside_via_traversal, False, "refused"),
    ("refused:symlink-to-logs",  _refused_symlink_to_logs,      False, "inside"),
]


@pytest.mark.parametrize(
    "label,factory,ok,err",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_write_gate(app_module, tmp_path, monkeypatch, label, factory, ok, err):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    saved_roots = list(app_module._ALLOWED_WRITE_ROOTS)
    saved_logs = app_module._LOGS_DIR_RESOLVED
    try:
        target = factory(app_module, tmp_path, None)
        if ok:
            app_module.assert_writable(target)
        else:
            with pytest.raises(app_module.WriteRefused) as exc:
                app_module.assert_writable(target)
            assert err.lower() in str(exc.value).lower(), exc.value
    finally:
        app_module._ALLOWED_WRITE_ROOTS.clear()
        app_module._ALLOWED_WRITE_ROOTS.extend(saved_roots)
        app_module._LOGS_DIR_RESOLVED = saved_logs


def test_write_gate_refuses_export_inside_logs(app_module, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    saved_roots = list(app_module._ALLOWED_WRITE_ROOTS)
    saved_logs = app_module._LOGS_DIR_RESOLVED
    try:
        app_module._set_write_policy(
            logs_dir=Path("/tmp"),
            cache_dir=tmp_path / "cache",
            export_dir=Path("/tmp"),
        )
        target = Path("/tmp") / "weelog-hindsight-20260101-120000.tsv"
        with pytest.raises(app_module.WriteRefused) as exc:
            app_module.assert_writable(target)
        assert "inside" in str(exc.value).lower() or "logs" in str(exc.value).lower(), (
            f"expected logs-overlap refusal, got: {exc.value}"
        )
    finally:
        app_module._ALLOWED_WRITE_ROOTS.clear()
        app_module._ALLOWED_WRITE_ROOTS.extend(saved_roots)
        app_module._LOGS_DIR_RESOLVED = saved_logs
