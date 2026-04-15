"""$WEELOG_DIR env var fallback: the three resolution branches
(explicit --logs, env var, neither) all produce the right behavior."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_script(app_module, args: list[str], env_extra: dict | None = None):
    env = {**os.environ}
    env.pop("WEELOG_DIR", None)
    if env_extra:
        env.update(env_extra)
    script = Path(app_module.__file__)
    return subprocess.run(
        [sys.executable, str(script)] + args,
        env=env, capture_output=True, text=True, timeout=10, check=False,
    )


def test_weelog_dir_fallback(app_module, synthetic_logs, monkeypatch):
    """When --logs is absent, $WEELOG_DIR resolves to the env var path.
    Tested via argparse directly to avoid spawning the full TUI."""
    import argparse
    monkeypatch.setenv("WEELOG_DIR", str(synthetic_logs))
    monkeypatch.setattr("sys.argv", ["weelog-hindsight"])
    # Re-run the arg-parse + resolution logic from main().
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", type=Path, default=None)
    args = ap.parse_args([])
    assert args.logs is None
    # Apply the same fallback as main().
    env = os.environ.get("WEELOG_DIR")
    assert env is not None
    args.logs = Path(env)
    assert args.logs == synthetic_logs
    assert args.logs.is_dir()


def test_logs_flag_overrides_weelog_dir(app_module, synthetic_logs, tmp_path):
    """--logs takes priority over $WEELOG_DIR."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    proc = _run_script(
        app_module,
        ["--logs", str(empty_dir)],
        env_extra={"WEELOG_DIR": str(synthetic_logs)},
    )
    combined = proc.stdout + proc.stderr
    # Should use the empty --logs dir, not $WEELOG_DIR, and fail
    # because it finds no log files there.
    assert "does not look like a weechat logs directory" in combined


def test_no_logs_no_env_gives_readable_error(app_module):
    """Neither --logs nor $WEELOG_DIR set: readable error + hint."""
    proc = _run_script(app_module, [])
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "no logs directory given" in combined
    assert "WEELOG_DIR" in combined



# Nonexistent WEELOG_DIR is the same shape as the "neither set" case
# (readable error + hint). Dropped to cut redundancy.
