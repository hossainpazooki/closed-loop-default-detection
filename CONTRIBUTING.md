# Contributing

Thanks for working on `closed-loop-default-detection`. This is a small,
deterministic, `sklearn`-only research harness; the bar is reproducibility, not
features. Keep changes tight and keep the docs honest.

## Dev install

From the repo root, in a clean virtual environment:

```bash
pip install -e ".[dev]"
```

On Windows the project venv lives at `.venv/Scripts/python.exe`; on Linux/macOS
use `.venv/bin/python`. Examples below use the Windows path — adjust as needed.

## Running the test suite

```bash
.venv/Scripts/python.exe -m pytest
```

There are **two CI gates**, and a change must satisfy both:

1. **Full suite** — every test, run under the pinned toolchain:

   ```bash
   .venv/Scripts/python.exe -m pytest
   ```

2. **Compat matrix** — the suite minus the float-exact tests, run across a range
   of supported `scikit-learn` / `numpy` versions:

   ```bash
   .venv/Scripts/python.exe -m pytest -m "not pinned"
   ```

The full run is the larger number; `-m "not pinned"` deselects the float-exact
tests and is what the compatibility matrix runs.

## The `pinned` marker

`HistGradientBoosting` float output shifts across `scikit-learn` releases, so a
handful of tests assert **exact or tight floating-point output** of the
calibrated PD model. These are marked `pinned` and are reproducible **only**
under the exact toolchain in `requirements-dev.txt` (the provenance pins under
which the committed artifacts and the byte-identity baseline were captured).

Rules:

- If a test asserts an exact float (or a frozen constant), mark it `pinned`.
- Run `pinned` tests under the `requirements-dev.txt` pins; do not assert
  float-exact behavior in an unpinned test.
- The compat matrix deselects `pinned` with `-m "not pinned"`; the full suite
  includes them.

> The byte-identity baseline test
> (`tests/test_loop_scm.py::test_flat_generator_byte_identical_to_pre_change_baseline`)
> asserts exact float equality of loop output against frozen constants. Treat it
> as load-bearing: refactors must leave its numbers untouched.

## Adding a correction lever

The closed loop's correction levers are **pluggable**: adding a lever is adding a
class. Subclass `Corrector` from `cldd.correctors`, give it a `name` and a
`control_priority`, and implement `apply`:

```python
from cldd.correctors import Corrector, CorrectorContext, CorrectionOutcome, LeverMetrics
from cldd import eval_default


class MyCorrector(Corrector):
    # Key under which this lever's metrics land in RoundResult.corrections.
    name = "my_lever"
    # The present corrector with the HIGHEST control_priority drives the loop's
    # control_metric; ties resolve to first-in-list. Built-ins are:
    #   naive=0, retrain=1, reweight=2, explore=3.
    control_priority = 5

    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        # ctx carries: seed, policy_threshold, severity, iteration,
        # exploration_rate, and make_train_cohort() -> (train_cohort, train_seed).
        model = eval_default.fit_observed_model(cohort, random_state=ctx.seed)
        scored = eval_default.score_pd_detection(model, cohort, ctx.policy_threshold)
        metrics = LeverMetrics.from_scored(scored)
        # info carries lever-specific extras (e.g. {"train_seed": ...}); {} is fine.
        return CorrectionOutcome(metrics=metrics, info={})
```

Use it by passing a list to the loop instead of `improve_mode`:

```python
from cldd.loop import SelectiveLabelsLoop
from cldd.correctors import NaiveCorrector

loop = SelectiveLabelsLoop(correctors=[NaiveCorrector(), MyCorrector()])
result = loop.run()
```

The list **must include a `NaiveCorrector`** (or a corrector named `"naive"`): the
loop projects it as the baseline `RoundResult.naive` and reads it each round, so a
list without one raises a `ValueError` at construction (a clear failure rather than
a mid-run `KeyError`).

When `correctors` is omitted, the loop builds the default list from
`improve_mode` / `exploration_rate` exactly as before — so the existing API is
unchanged. See `examples/quickstart.py` for a runnable end-to-end demo.

Determinism note: each built-in lever uses an **independent** RNG seed (naive and
reweight use the loop seed; retrain uses its disjoint train seed; explore uses a
dedicated stream), so lever order does not change any numbers. Keep new levers
seeded explicitly from `ctx` for the same reason.

## Commit and branch conventions

- **Branch per change.** Branch off the main branch for anything non-trivial
  rather than committing to it directly.
- **Conventional commits.** One commit maps to one task; use a
  conventional-commit prefix and an imperative ~50-char subject:

  ```
  feat: add exploration-budget correction lever
  fix: guard reweight against all-approved cohorts
  docs: clarify the pinned-test gate in CONTRIBUTING
  ```

  Add a body only when the *why* isn't obvious from the subject.
- Don't introduce float-exact assertions without the `pinned` marker, and don't
  let a code change leave a doc, README, or `CLAUDE.md` stale — update them in
  the same change.
