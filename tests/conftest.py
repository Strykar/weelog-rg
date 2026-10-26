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
SCRIPT_PATH = REPO_ROOT / "bin" / "weelog-rg"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _isolate_index_cache(monkeypatch, tmp_path_factory):
    # Subprocess tests inherit os.environ; without this the suite writes the real ~/.cache/weelog-rg.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("xdg-cache")))


@pytest.fixture(scope="session")
def app_module():
    loader = SourceFileLoader("weelog_rg_script", str(SCRIPT_PATH))
    spec = importlib.util.spec_from_loader("weelog_rg_script", loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["weelog_rg_script"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def synthetic_logs(tmp_path: Path) -> Path:
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
    (dated / "alice.01-02.log").write_text(
        "2026-01-02 12:00:00\talice\tprivate hello\n"
        "2026-01-02 12:00:05\tlocal-user\tprivate reply\n",
        encoding="utf-8",
    )

    legacy_plain = tmp_path / "irc.legacy-network.#oldchan.weechatlog"
    legacy_plain.write_text(
        "2024-05-01 08:00:00\tdave\ttext in the active legacy file\n"
        "2024-05-02 08:00:00\teve\tanother legacy line\n",
        encoding="utf-8",
    )
    gz_path = tmp_path / "irc.legacy-network.#oldchan.weechatlog.1.gz"
    with gzip.open(gz_path, "wt", encoding="utf-8") as f:
        f.write("2024-01-15 08:00:00\tfrank\tarchived gzip line\n")

    if shutil.which("zstd"):
        zst_path = tmp_path / "irc.legacy-network.#oldchan.weechatlog.2.zst"
        plain = b"2023-08-01 08:00:00\tgrace\tarchived zstd line\n"
        zst_path.write_bytes(subprocess.check_output(
            ["zstd", "-q"], input=plain,
        ))

    (tmp_path / "core.weechat.weechatlog").write_text(
        "2024-05-01 07:00:00\t--\tWeeChat startup\n",
        encoding="utf-8",
    )

    (tmp_path / "irc.server.legacy-network.weechatlog").write_text(
        "2024-05-01 07:00:00\t--\t-- server notice --\n",
        encoding="utf-8",
    )

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

    (dated / "bouncerserv.01-02.log").write_text(
        "2026-01-02 10:00:00\tBouncerServ\tconnected to irc.example.net\n"
        "2026-01-02 10:00:01\tBouncerServ\tnetwork example-network: 3 channels\n",
        encoding="utf-8",
    )
    (tmp_path / "irc.legacy-network.bouncerserv.weechatlog").write_text(
        "2024-05-01 07:00:00\tBouncerServ\thistory playback message\n",
        encoding="utf-8",
    )

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
    import _fuzz_lib
    original = _fuzz_lib.patch_debounce_to_immediate(app_module)
    yield
    app_module.WeelogRg._schedule_search = original
