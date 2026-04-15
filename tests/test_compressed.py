"""Compression coverage: .gz is exercised elsewhere via the existing
fixture, but .zst hits a different code path (subprocess zstdcat plus
the _ProcReader cleanup). These tests fail loudly on systems where the
zstd binary is missing, so they're skipped there."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    shutil.which("zstd") is None,
    reason="zstd binary not available; conftest skipped the .zst fixture",
)


def test_zst_indexed_as_compressed(app_module, synthetic_logs):
    idx = app_module.build_index(synthetic_logs)
    by_name = {Path(entry.path).name: entry for entry in idx}
    e = by_name["irc.legacy-network.#oldchan.weechatlog.2.zst"]
    assert e.compressed is True
    assert e.network == "legacy-network"
    assert e.buffer == "#oldchan"


async def test_zst_search_via_rg(app_module, synthetic_logs):
    """rg -z handles zst transparently; the include_compressed gate
    must let the .zst path through, and the result must parse."""
    idx = app_module.build_index(synthetic_logs)
    q = app_module.Query(text="archived zstd", include_compressed=True)
    matches = [
        m async for m in
        app_module.run_search(q, app_module.select_files(idx, q))
    ]
    assert len(matches) == 1
    m = matches[0]
    assert m.path.endswith(".zst")
    assert m.who == "grace"
    assert "archived zstd" in m.message


def test_zst_open_log_reaps_subprocess(app_module, synthetic_logs):
    """open_log on a .zst path returns a _ProcReader that reaps the
    backing zstdcat subprocess on close. Verifies the leak fix by
    checking the proc has exited after the reader's `with` block."""
    idx = app_module.build_index(synthetic_logs)
    by_name = {Path(entry.path).name: entry for entry in idx}
    zst = by_name["irc.legacy-network.#oldchan.weechatlog.2.zst"]

    reader = app_module.open_log(zst.path)
    assert isinstance(reader, app_module._ProcReader)
    proc = reader._proc
    with reader as f:
        lines = list(f)
    assert any("grace" in ln for ln in lines)
    # Subprocess must have a returncode set after close (i.e., reaped).
    assert proc.returncode is not None, "zstdcat was not waited on"
