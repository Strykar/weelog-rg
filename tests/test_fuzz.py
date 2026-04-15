"""Headless Textual fuzz harness (pytest wrapper).

Drives the TUI via Textual's Pilot API with random knob permutations
and checks state-sync invariants after each action. Caught the
stale-preview and mid-stream-row-list-mismatch bugs during development.

Invariants and action dispatchers live in `_fuzz_lib.py` so the
standalone `scripts/fuzz.py` harness can't drift away from this one.
Marked slow (~20-60 s per seed); skip with `pytest -m "not slow"`.
"""
from __future__ import annotations

import random
import traceback

import pytest

import _fuzz_lib  # added to sys.path by conftest.py


N_ITERATIONS = 50
SEEDS = (1, 42)


async def _run_seed(app_module, synthetic_logs, seed: int, iterations: int):
    random.seed(seed)
    index, stats = app_module.load_or_build_index(synthetic_logs)
    app = app_module.Hindsight(synthetic_logs, index, theme="dark",
                               index_stats=stats)

    violations: list[_fuzz_lib.Violation] = []
    errors: list[str] = []

    async with app.run_test(size=(200, 60)) as pilot:
        await pilot.pause(0.2)
        for _ in range(iterations):
            sel, kind = random.choice(_fuzz_lib.ACTIONS)
            try:
                action = await _fuzz_lib.step(pilot, sel, kind)
            except Exception:
                errors.append(traceback.format_exc())
                continue
            try:
                await app.workers.wait_for_complete()
                await pilot.pause(0.05)
                violations.extend(
                    await _fuzz_lib.check_invariants(app, app_module, action)
                )
            except Exception:
                errors.append(traceback.format_exc())
                continue
    return violations, errors


@pytest.mark.slow
@pytest.mark.parametrize("seed", SEEDS)
async def test_fuzz(app_module, synthetic_logs, debounce_immediate, seed):
    violations, errors = await _run_seed(
        app_module, synthetic_logs, seed, N_ITERATIONS,
    )
    assert not violations, "\n".join(str(v) for v in violations[:10])
    assert not errors, "\n".join(errors[:3])
