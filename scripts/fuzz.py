#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["textual==8.2.3", "rich==15.0.0"]
#
# [tool.uv]
# exclude-newer = "2026-10-26T00:00:00Z"
# ///
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import random
import sys
import traceback
from importlib.machinery import SourceFileLoader
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "tests"))
import _fuzz_lib  # noqa: E402


def load_app_module(path: Path):
    loader = SourceFileLoader("weelog_rg_app", str(path))
    spec = importlib.util.spec_from_loader("weelog_rg_app", loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["weelog_rg_app"] = mod
    spec.loader.exec_module(mod)
    return mod


async def run(logs_dir: Path, iterations: int, seed: int) -> int:
    random.seed(seed)
    target = SCRIPT_DIR.parent / "bin" / "weelog-rg"
    if not target.exists():
        import shutil
        found = shutil.which("weelog-rg")
        if not found:
            sys.exit(
                f"error: could not find bin/weelog-rg relative to "
                f"{SCRIPT_DIR} or on $PATH"
            )
        target = Path(found)
    if not logs_dir.is_dir():
        sys.exit(f"error: {logs_dir} is not a directory")

    mod = load_app_module(target)
    _fuzz_lib.patch_debounce_to_immediate(mod)

    index, stats = mod.load_or_build_index(logs_dir)
    app = mod.WeelogRg(logs_dir, index, theme="dark", index_stats=stats)

    violations: list[_fuzz_lib.Violation] = []
    errors: list[str] = []

    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)
        for i in range(iterations):
            sel, kind = random.choice(_fuzz_lib.ACTIONS)
            try:
                action = await _fuzz_lib.step(pilot, sel, kind)
            except Exception:
                errors.append(f"action {sel}/{kind}:\n{traceback.format_exc()}")
                continue
            try:
                await app.workers.wait_for_complete()
                await pilot.pause(0.05)
                violations.extend(
                    await _fuzz_lib.check_invariants(app, mod, action)
                )
            except Exception:
                errors.append(f"invariant-check raised:\n{traceback.format_exc()}")
                continue

            if i % 10 == 9:
                print(f"  [{i+1}/{iterations}] violations so far: "
                      f"{len(violations)}, errors: {len(errors)}",
                      file=sys.stderr)

    print(f"\n=== fuzz summary (seed={seed}, {iterations} iterations) ===")
    print(f"invariant violations: {len(violations)}")
    print(f"uncaught errors:      {len(errors)}")
    if violations:
        print("\n--- violations ---")
        seen = set()
        for v in violations:
            key = (v.invariant, v.detail.split("(")[0])
            if key in seen:
                continue
            seen.add(key)
            print(f"  {v}")
        print(f"  ({len(violations)} total, {len(seen)} unique)")
    if errors:
        print("\n--- first 3 errors ---")
        for e in errors[:3]:
            print(e)
    return 0 if not violations and not errors else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", type=Path, required=True)
    ap.add_argument("-n", "--iterations", type=int, default=80)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rc = asyncio.run(run(args.logs, args.iterations, args.seed))
    sys.exit(rc)


if __name__ == "__main__":
    main()
