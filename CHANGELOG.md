# Changelog

All notable changes to `closed-loop-default-detection` (import name `cldd`) are
recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/). Version `0.1.0` is the
initial **alpha**, published to [PyPI](https://pypi.org/project/closed-loop-default-detection/).

## [0.2.0] — unreleased (alpha)

The **expected-maximum-profit (EMP) measurement layer**: the loop now reports what being
wrong on the declined population *costs*, not only whether it is miscalibrated.

### Added
- **`cldd.emp`** — two EMP variants over the same in-process scores, pure numpy, zero RNG:
  `empc_literature` (Verbraken et al. 2014 closed form over the ROC convex hull, Eqs. 13/15,
  with the source-verified `EMPC_P0/EMPC_P1/EMPC_ROI` prior) and `emp_harness` (this
  harness's own loan economics + planted per-row default timing; SCM cohorts only — flat
  cohorts plant no timing and return `None`). Both are ranking-only: invariant to any
  strictly monotone transform of the score.
- **EMP columns** on `SubgroupMetrics` / `LeverMetrics` and in the frontier CSVs, plus an
  EMP-vs-severity panel on the frontier plot.
- **`RoundResult.exploration_cost`** — the exploration lever's bought labels priced in
  dollars (also a new column in `artifacts/exploration_frontier.csv`).
- **`f1_emp_cutoff`** — F1 at the EMP-optimal cutoff, reported alongside the existing F1 at
  the arbitrary `POLICY_PD_THRESHOLD = 0.5` (which is retained for continuity and now
  documented as diagnostic-only).
- **`scripts/run_frontier_sweep.py`** — the frontier's distribution across the 25-seed set,
  replacing a single-seed point estimate; one subprocess per run, resumable.
- 26 new tests (149 total), including hand-computed convex-hull cases, monotone-invariance,
  degenerate-timing cases, and cross-process float determinism.

### Notable results
**The frontier is a distribution, not a point.** Running the loop across the full 25-seed set
shows the published single-seed frontier (0.4, seed 42) is the *optimistic* end: in the SCM
world the median frontier is **0.2**, with only 11/25 seeds reaching 0.4 (flat: median 0.4,
15/25). The mechanism is unchanged — the unobserved confounder still explains the failure —
but the boundary is honestly **0.2–0.4 depending on the draw**. The prior headline was a valid
instance, not a center.

**The two EMP variants disagree, and the disagreement is the finding**: the literature's
convenience prior assumes `ROI = 0.2644` where this 60-day daily-ACH loan structure actually
returns `0.0875`, and places 55% of defaults at full recovery where the harness plants ~1%.
Priced honestly, profit on the declined pool collapses toward zero as selection severity
rises; priced by the standard prior, it appears to grow. See the README's *Pricing the
frontier* section, including the caveat that `emp_h` rests on **planted, unfitted** default
timing — a verified experiment, not a verified result.

### Changed
- EMP is a **reporting axis only** — ECE remains the sole loop-control metric. Loop
  decisions, the frontier, and every v1 column of the committed frontier CSVs are unchanged
  (byte-identity verified against the previous artifacts; EMP columns are strictly appended).
- Renamed the loop driver and its artifacts to drop the pre-release lineage naming:
  `scripts/run_clue.py` → `scripts/run_loop.py`, and the committed
  `artifacts/clue_frontier*.{csv,png}` → `artifacts/loop_frontier*.{csv,png}`
  (history-preserving renames; CSV contents are byte-identical). Module docstrings
  and package metadata no longer reference the originating project.
- Moved the accompanying article `FABLE.md` to `docs/assessment.md` (history-preserving
  move; contents unchanged — it is a dated provenance snapshot, excluded from the
  Sphinx build like the other dated records).

### Fixed
- `ExplorationCorrector` raised `ZeroDivisionError` when constructed with
  `exploration_rate = 0.0` (the inverse-propensity weight was evaluated eagerly even though
  no row can be explored). Unreachable through `SelectiveLabelsLoop`, which only adds the
  lever when the rate is positive, so no committed number changes.

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
