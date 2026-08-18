# Changelog

All notable changes to `closed-loop-default-detection` (import name `cldd`) are
recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/). Version `0.1.0` is the
initial **alpha**, published to [PyPI](https://pypi.org/project/closed-loop-default-detection/).

## [Unreleased]

v4 Option A — the `unobserved_strength` × severity surface (spec
`docs/superpowers/specs/2026-07-29-cldd-v4-option-a-surface-design.md`, Rev 1.2):

- **Two additive knobs**, byte-exact at their defaults (differential tests enforce it):
  `SelectiveLabelsLoop(generator_kwargs=...)` forwards world-construction overrides to the
  loop's generator, and `run_counterfactual_eval(unobserved_strength=...)` sets the
  confounder strength on the eval side. Neither changes any existing code path when unset.
- **Surface sweep driver** (`scripts/run_surface_sweep.py`): resumable subprocess-per-run
  sweep over the 6-point strength grid {0, .2, .4, .55, .7, 1.0} × both worlds (300 loop
  runs) and × severities (450 evals), with a mechanical pilot gate (byte-match +
  non-vacuity + budget trip-wire) required before any matrix launch. Artifacts:
  `artifacts/surface_frontier.csv`, `artifacts/surface_counterfactual.csv`.
- **Fail-closed analysis** (`scripts/surface_stats.py`): recomputes every to-be-published
  surface number from the two committed CSVs, halts on missing cells, and enforces the I-1
  byte-identity embed gate (default-strength cells string-equal to the recorded-environment
  spaced re-baseline `*_v4env.csv`; environment manifest `artifacts/surface_env.json`).
  Writes `artifacts/surface_stats.csv`. Spec Rev 1.2 corrects Rev 1.1's counterfactual
  max-abs drift figure (4.16e-17 → 6.94e-17; conclusions unchanged).
- **Verdicts + qualification (spec §3, same change):** all four pre-registered hypotheses
  came back **not confirmed** (triple-recomputed per §9 gate 6 — script, lead, and an
  independent skeptic, in full agreement), so the README's one-cause mechanism claim is
  withdrawn as measured and replaced by a registered v4 section: the wall stands at
  strength 0 (flat 25/25 seeds at 0.4, confounder off), the axis bites only at strength
  1.0 (observed post-hoc, a future pre-registration rather than a confirmation), and the
  counterfactual gap runs opposite the predicted direction. New `surface-verdicts` claim
  in the doc-number gate recomputes every quoted figure from both surface CSVs (added to
  `ARTIFACTS_READ`, covered by the tracked-status guard) and refuses the "not confirmed"
  literal unless all four floor checks still fail. Long-form in `how-it-works.md`; gate
  row in `validation.md`; knob rows in `configuration.md`.
- **I-1 frontier leg now fails closed on absent cells**: a cell missing from *both* sides
  of the byte-identity comparison previously zipped over nothing and passed silently
  (latent — never reachable in a live run; `docs/learnings/2026-08-18-fail-closed-gate-
  with-one-leg-that-isnt.md`). One-line guard + a regression test pinning both legs;
  suite 230.

Post-publication robustness (assessment Part III, items III.2-1 and III.3):

- **Spaced-seed replication** (`scripts/run_spaced_sweeps.py`): both the counterfactual and
  frontier sweeps re-run on the seed set {1000 + 16i, i = 0..24}, seed-disjoint within each
  generator/severity cell, written to the new `artifacts/seed_sweep_spaced.csv` /
  `artifacts/frontier_sweep_spaced.csv` — the committed originals untouched. The severity-0.4
  counterfactual advantage survives (+0.0129 ± 0.0102, 22/25 positive, Wilcoxon p = 1.6e-6).
  Source audit (adversarially verified): a counterfactual run consumes only `{s, s+1000}`, so
  the original counterfactual set was already cross-run independent within severity —
  assessment Part III critique 1's premise applied to the **loop sweep only** (10 colliding
  run pairs per generator on the old set, confirmed from consumed iterations); the p shift
  1.5e-7 → 1.6e-6 is replicate variability, not de-biasing. On the seed-disjoint loop sweep
  the overlapping set's SCM frontier median of 0.2 does **not** replicate: both worlds center
  at 0.4 (flat 18/25, SCM 15/25 at 0.4). README updated to quote both designs.
  `paired_significance.py` gains `--sweep-csv`/`--out-csv` (defaults unchanged and verified
  byte-identical); its severity-1.0 closing note now computes its magnitude from the data
  instead of hardcoding +0.0017.
- **Doc-number gate** (`scripts/check_doc_numbers.py` + `tests/test_doc_numbers.py`): every
  empirical figure quoted in the README now recomputes from a committed artifact in CI, at
  the precision the README quotes; fail-closed, and the planted-mismatch test proves it can
  fire. Its first run caught the H4 note quoting "≤1e-10" where the measured max error is
  1.0000000567e-10 (README now quotes the measured value), a stale test count (149 → 209),
  and a stale Status/citation version (0.2.0 → 0.3.0). Its first CI run then caught a
  deeper one: `artifacts/feedback_profit_sweep.csv` (and `feedback_sweep_stats.csv`) had
  **never been committed** — gitignore-default-denied since v3, so the "recomputes from a
  committed CSV" claim was clone-broken from the start; both are now committed, and a new
  guard test asserts every artifact the gate reads is git-tracked (the repo's third
  unexcepted-artifact incident, now mechanized away).

## [0.3.0] — 2026-07-22 (alpha)

The **feedback-loop profit decomposition**: three arms price *why* the closed loop costs
money. `FeedbackLoop` gains two additive, byte-exact-default flags — `retrain=False` (the
frozen arm: generation-0 model deployed forever, exploration from generation 1 only) and
`policy_mode="prior"` (prior-policy funding, model trained for metrics only) — plus
`book_profit`/`explored_profit` on `GenerationResult` via `realized_book_profit`
(full-cohort exposure denominator; **cohort-basis day-90 imputation**, spec Rev 2.1/2.2:
the pricing basis is a planted cohort property, which makes the H4 identity exact rather
than tolerance-fudged). New: `scripts/run_feedback_sweep.py` (450-run shard-per-run matrix,
subprocess-per-run, `--quick` pilot gate) and `scripts/feedback_sweep_stats.py` (recomputes
every published number from the committed CSV; exits non-zero when H4 fails — publication
mechanically blocked). Results, from `artifacts/feedback_profit_sweep.csv` (25 seeds,
distributions only, planted-timing label attached): **H1 confirmed** — feedback
accumulation costs the funded book (median paired deficit −0.0028, 24/25 seeds, Holm
p 2.3e-06, clears the prior-arm noise floor); **H2 not confirmed and opposite in measured
direction** (+0.0119, 0/25); **H3/H3a not confirmed** (5% exploration does not pay for
itself in-window); **H4 identity ≤ 1e-10** on all 900 checked rows; the declined-ECE alarm
fires at generation 1–2 in every ε=0 run at 25 seeds (the v2-banked question, answered).
54 new tests (203 total). The v3 default-path
compatibility gate is **differential**: the pre-v3 `feedback.py` is reconstructed from its
git blob and both paths run in one process, replacing a machine-derived sha256 baseline
that was not portable across OS/numpy floats (it had broken CI on every non-matching
environment); a non-vacuity guard asserts the reconstructed module really is pre-v3.

## [0.2.0] — 2026-07-14 (alpha)

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
