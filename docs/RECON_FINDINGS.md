# Recon findings: path to alpha for the validation harness

Purpose: record the results of a rigor `/recon` (fan-out recon -> refute -> synthesize) audit of this
harness answering "how can the validation harness be taken to alpha?", plus the three fixes applied.
Date: 2026-07-01. Status tags are literal; the implemented-vs-planned boundary is meant to be visible.

## Corrections to prior assumptions

Two premises the audit inherited turned out to be wrong. Both corrections were re-run by the
orchestrator against raw sources, not merely reported by an agent.

- **The fidelity gate DOES pass on the maintainer's machine.** With the real Intuit dataset present,
  `scripts/check_fidelity.py` prints `OVERALL: PASSED` over real labeled n=51,722 with 0 failures.
  The prior "unverified because `train.csv` is absent" premise was FALSE on this machine.
- **The section 3 g-computation headline REPRODUCES deterministically.** A fresh
  `run_counterfactual_eval(seed=42)` matches the committed `artifacts/seed_sweep_25.csv` seed-42 rows
  exactly to 10 decimals (sev 0.4 `strong_gap=0.0078823063...`, sev 1.0 `strong_gap=0.0017032393...`).
  A skeptic's "does-not-reproduce" verdict was a FALSE REFUTATION: it came from running
  `scripts/run_seed_sweep.py --quick` (reduced config) against a full-config artifact.

## Fixed in this change (items 1, 3, 5)

- **Item 1 — fidelity gate portability [FIXED].**
  Before: `DEFAULT_DATA_DIR` was a hardcoded author absolute path.
  After: resolves from the `CLDD_DATA_DIR` env var, with a clear error naming `CLDD_DATA_DIR` when the
  data is absent (the real dataset is private and unshipped).
- **Item 3 — honest fidelity label [FIXED].**
  Before: the gate implied full distributional fidelity.
  After: relabeled **MARGINAL** — it validates univariate marginals only and does NOT check the
  joint/causal distribution. Updated in the verdict string, report header, module docstring, and README.
- **Item 5 — dev-dependency Python floor [FIXED].**
  Before: `requirements-dev.txt` pinned `numpy==2.4.6` / `scikit-learn==1.9.0` with no note that they
  need Python >=3.11.
  After: documents the >=3.11 requirement for the pinned provenance set and points 3.10 users to
  `pip install -e ".[dev]"`. `requires-python>=3.10` is left unchanged because CI tests 3.10-3.13 via
  the range install.

## Open path-to-alpha items

| Item | Severity | Status | Action |
|------|----------|--------|--------|
| CI never runs the fidelity gate (real data can't exist on Linux/macOS runners) | major | [OPEN] | Gate real data in CI via a fixture or synthetic fixture path; treat green-only-locally as a known gap. |
| "90 passed / 0 skipped" is machine-specific; `tests/test_fidelity.py` skips data-backed tests when dataset absent | major | [OPEN] | Report the skip-aware count in CI; stop quoting the local all-pass number as universal. |
| No coverage tooling; `model_pd.py` (detector) and `eval_default.py` (measure stage) have no dedicated tests | major | [OPEN] | Add coverage tooling and dedicated test files for both modules. |
| `Development Status :: 4 - Beta` on an unreleased, untagged, not-on-PyPI 0.1.0 | minor | [OPEN] | Change classifier to `3 - Alpha`. |
| No CHANGELOG; `cldd.__version__` not exposed; `CalibratedPDModel` not in `__all__`; no `py.typed` despite `Typing :: Typed` | minor | [OPEN] | Add CHANGELOG, expose `__version__`, add the detector to `__all__`, ship `py.typed`. |
| `Development Status` build/install baseline | — | [BUILD-OK] | Clean PEP 517 wheel builds (`pip wheel .` -> 0.1.0, all 13 modules); public repo clone + `pip install -e .` works; `examples/quickstart.py` runs to completion (exit 0). No action. |

## Explicit non-goal

- **sklearn-API compatibility (BaseEstimator / `check_estimator`) is deliberately NOT pursued** [NON-GOAL].
  The estimators are loop-internal; treat this as a post-alpha optional extension, not an alpha blocker.

## How this was verified

- 5 recon dimensions were fanned out in parallel under one shared return schema.
- Each load-bearing finding was refuted by an independent skeptic; only survivors are recorded above.
- The two corrections (the fidelity gate pass and the seed-42 g-computation reproduction) were re-run
  by the orchestrator against raw sources, not accepted on an agent's word.
- One skeptic FALSE REFUTATION (the "does-not-reproduce" g-comp verdict, caused by a `--quick` reduced
  config) was caught precisely by that orchestrator re-run.
