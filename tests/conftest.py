"""Shared test fixtures.

Loads the script under test via importlib since it has no `.py` suffix
and lives outside a Python package (by design - it's also a drop-in
executable). Builds an on-disk synthetic log fixture that covers every
format quirk the parser must handle.
"""
from __future__ import annotations

import gzip
import importlib.util
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "bin" / "weelog-hindsight"

# Make tests/_fuzz_lib.py importable from any test file without __init__.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(scope="session")
def app_module():
    """Import bin/weelog-hindsight as an importable module."""
    loader = SourceFileLoader("weelog_hindsight_script", str(SCRIPT_PATH))
    spec = importlib.util.spec_from_loader("weelog_hindsight_script", loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["weelog_hindsight_script"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def synthetic_logs(tmp_path: Path) -> Path:
    """Produce a miniature weechat-like log tree under tmp_path.

    Covers both layouts + rotation + event/PM/chat lines + unicode.
    """
    # Dated layout: 2026/<network>/<buffer>.MM-DD.log
    dated = tmp_path / "2026" / "example-network"
    dated.mkdir(parents=True)
    (dated / "#channel-one.01-02.log").write_text(
        "2026-01-02 10:00:00\t▬▬▶\talice (~a@example.net) has joined #channel-one\n"
        "2026-01-02 10:00:01\t--\tTopic for #channel-one is \"hello world\"\n"
        "2026-01-02 10:00:30\talice\tgood morning\n"
        "2026-01-02 10:01:00\tbob\tmorning - https://example.org/path?q=1\n"
        "2026-01-02 10:02:00\tcarol\tκαλημέρα 😀\n",
        encoding="utf-8",
    )
    (dated / "#channel-one.01-03.log").write_text(
        "2026-01-03 09:00:00\talice\tday two message\n"
        "2026-01-03 09:05:00\tbob\treply with text\n",
        encoding="utf-8",
    )
    # PM buffer - no # prefix; under dated layout
    (dated / "alice.01-02.log").write_text(
        "2026-01-02 12:00:00\talice\tprivate hello\n"
        "2026-01-02 12:00:05\tlocal-user\tprivate reply\n",
        encoding="utf-8",
    )

    # Legacy flat: <plugin>.<name>.weechatlog (+ rotated .gz)
    legacy_plain = tmp_path / "irc.legacy-network.#oldchan.weechatlog"
    legacy_plain.write_text(
        "2024-05-01 08:00:00\tdave\ttext in the active legacy file\n"
        "2024-05-02 08:00:00\teve\tanother legacy line\n",
        encoding="utf-8",
    )
    # Rotated gzipped sibling
    gz_path = tmp_path / "irc.legacy-network.#oldchan.weechatlog.1.gz"
    with gzip.open(gz_path, "wt", encoding="utf-8") as f:
        f.write("2024-01-15 08:00:00\tfrank\tarchived gzip line\n")

    # Rotated zstd sibling, only when zstd is on PATH (tests that need
    # it should pytest.skip if `zst_present` is False).
    if shutil.which("zstd"):
        zst_path = tmp_path / "irc.legacy-network.#oldchan.weechatlog.2.zst"
        plain = b"2023-08-01 08:00:00\tgrace\tarchived zstd line\n"
        zst_path.write_bytes(subprocess.check_output(
            ["zstd", "-q"], input=plain,
        ))

    # Core/meta buffer (two-component flat name, no network)
    (tmp_path / "core.weechat.weechatlog").write_text(
        "2024-05-01 07:00:00\t--\tWeeChat startup\n",
        encoding="utf-8",
    )

    # IRC server buffer (irc.server.<network>.weechatlog)
    (tmp_path / "irc.server.legacy-network.weechatlog").write_text(
        "2024-05-01 07:00:00\t--\t-- server notice --\n",
        encoding="utf-8",
    )

    # ZNC module buffers, both affix variants (ZNC StatusPrefix config
    # lets admins pick either; both appear in the wild):
    (tmp_path / "irc.legacy-network.*status.weechatlog").write_text(
        "2024-05-01 07:00:00\t*status\tZNC status message\n",
        encoding="utf-8",
    )
    (tmp_path / "irc.legacy-network.status*.weechatlog").write_text(
        "2024-05-01 07:00:00\tstatus*\tZNC status message (suffix)\n",
        encoding="utf-8",
    )
    (tmp_path / "irc.legacy-network.*controlpanel.weechatlog").write_text(
        "2024-05-01 07:00:00\t*controlpanel\tZNC controlpanel\n",
        encoding="utf-8",
    )

    # Soju bouncer control buffer. On-disk filename is lowercase
    # (logger.file.name_lower_case default on), but the who field
    # in the log line preserves IRC's mixed case (BouncerServ).
    # Dated layout under an existing network:
    (dated / "bouncerserv.01-02.log").write_text(
        "2026-01-02 10:00:00\tBouncerServ\tconnected to irc.example.net\n"
        "2026-01-02 10:00:01\tBouncerServ\tnetwork example-network: 3 channels\n",
        encoding="utf-8",
    )
    # Legacy layout under a different network:
    (tmp_path / "irc.legacy-network.bouncerserv.weechatlog").write_text(
        "2024-05-01 07:00:00\tBouncerServ\thistory playback message\n",
        encoding="utf-8",
    )

    # Network services (atheme/anope-style bots): appear as unprefixed
    # query buffers named after the service. Case-insensitive match
    # in the classifier.
    (tmp_path / "irc.legacy-network.chanserv.weechatlog").write_text(
        "2024-05-01 07:00:00\tChanServ\tyou are now identified\n",
        encoding="utf-8",
    )
    (tmp_path / "irc.legacy-network.nickserv.weechatlog").write_text(
        "2024-05-01 07:00:00\tNickServ\tregistered nickname\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def debounce_immediate(app_module):
    """Shrink the 300 ms search debounce to ~0 so
    `workers.wait_for_complete` doesn't race the timer."""
    import _fuzz_lib
    original = _fuzz_lib.patch_debounce_to_immediate(app_module)
    yield
    app_module.Hindsight._schedule_search = original
