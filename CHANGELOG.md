# Changelog

All notable changes to `closed-loop-default-detection` (import name `cldd`) are
recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/). Version `0.1.0` is the
initial **alpha**, published to [PyPI](https://pypi.org/project/closed-loop-default-detection/).

## [Unreleased]

### Changed
- Renamed the loop driver and its artifacts to drop the pre-release lineage naming:
  `scripts/run_clue.py` → `scripts/run_loop.py`, and the committed
  `artifacts/clue_frontier*.{csv,png}` → `artifacts/loop_frontier*.{csv,png}`
  (history-preserving renames; CSV contents are byte-identical). Module docstrings
  and package metadata no longer reference the originating project.
- Moved the accompanying article `FABLE.md` to `docs/assessment.md` (history-preserving
  move; contents unchanged — it is a dated provenance snapshot, excluded from the
  Sphinx build like the other dated records).

## [0.1.0] — 2026-07-03 (alpha)

Initial alpha of the selective-labels default-detection harness.

### Added
- **Closed loop** (`SelectiveLabelsLoop`): the generate → measure → improve → regenerate
  cycle that escalates selection severity to find a PD model's operating frontier.
- **Pluggable correction levers** (`Corrector` ABC): naive, IPW reweight, disjoint
  retrain, and exploration, plus the reject-inference correctors.
- **Two synthetic worlds**: the flat `SyntheticBorrowerGenerator` and the fitted, layered
  `StructuralBorrowerGenerator` (SCM).
- **Marginal-fidelity gate** (`cldd.fidelity`): compares SCM cohorts against real-data
  *univariate marginals*.
- **Counterfactual validator**: a deployable g-computation estimator vs. naive conditioning.
- **Feedback / exploration** simulation and observable positivity diagnostics.
- Top-level export of the calibrated PD detector, `CalibratedPDModel`.
- **`CalibratedPDClassifier`**: a scikit-learn estimator face for the calibrated PD
  detector (`fit`/`predict_proba`/`predict`, `clone`, `get_params`/`set_params`,
  `classes_`, `n_features_in_`, `NotFittedError`). Binary-only by design; byte-identical
  probabilities to `train_pd_model` under the same seed; the full `check_estimator`
  battery passes on scikit-learn 1.7.2–1.9.0 (`tests/test_sklearn_compat.py`, run on
  the CI compat matrix).
- Packaging hygiene: `cldd.__version__`, a PEP 561 `py.typed` marker, and coverage
  tooling (`pytest --cov=cldd`).
- Dedicated regression tests for `model_pd.py` and `eval_default.py`.

### Changed
- Fidelity gate output and docs relabeled **MARGINAL** so "fidelity PASSED" no longer
  reads as joint/causal fidelity.
- `DEFAULT_DATA_DIR` is now overridable via the `CLDD_DATA_DIR` environment variable; the
  private dataset is not shipped, and an absent dataset raises a clear, actionable error.
- Development-status classifier: Beta → **Alpha**.

### Fixed
- CI float-determinism: a version-sensitive exploration test is marked `pinned`, and the
  frozen-value asserts compare with a tolerance (pinning dependency *versions* does not pin
  the BLAS/CPU, so HistGradientBoosting output can drift by ~1 ULP across machines).
- The strict Sphinx (`-W`) docs build no longer breaks on the internal findings doc.

### Notes / known limitations
- The real-data fidelity gate needs a **private** dataset and therefore **does not run on
  public CI**; coverage of `cldd/fidelity.py`'s data-loading path is correspondingly low on
  CI by design. See the README "Tests, validation, and docs" section.
- scikit-learn-estimator API compatibility is provided **through `CalibratedPDClassifier`
  only** (binary-only, sample-weight equivalence not guaranteed — see README "sklearn
  compatibility"). The loop-internal functional API (`train_pd_model`, correctors, the
  loop itself) remains outside the sklearn estimator contract by design.
