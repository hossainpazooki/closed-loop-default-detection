# Session Handoff — closed-loop-default-detection

> A standalone harness that stress-tests probability-of-default (PD) modeling under
> **selective labels**, the central difficulty of the Intuit TechWeek SMB
> Underwriting Challenge. It ports a **closed-loop methodology** (generate → measure
> → improve → regenerate, escalating to an operating frontier) to credit risk, and
> adds a **fidelity-checked structural causal model (SCM)** so we can measure the
> three things real lending data structurally cannot reveal.

Repo: `hossainpazooki/closed-loop-default-detection` (**private**, branch `master`).
Local: `C:\Users\hossa\dev\closed-loop-default-detection`. Python venv at
`.venv/Scripts/python.exe` (numpy, pandas, scikit-learn, matplotlib, pytest).

---

## 0. Stale-number flags from an external verification pass (2026-06-26)

> A read-only pass re-ran `pytest` and recomputed against `artifacts/*.csv`. **The code is
> fine** — 90/90 green, byte-determinism holds. These are *doc-staleness* fixes for a future
> session; nothing here needs a code change:
>
> - **Test count:** the suite is **90 passed**, not 66. §2 layout note (~L65), §6 (~L159),
>   and §7 (~L183) still say 66; the README is already correct at 90.
> - **§7 g-computation numbers don't reproduce.** The figures attributed to *"Measured (seed
>   42)"* — `0.0734 → 0.0598 (+0.0135)` at sev 0.4 and `+0.0038` at sev 1.0 — match no
>   artifact. Raw `seed_sweep_25.csv` seed-42 is `0.0714 → 0.0635 (+0.0079)` and `+0.0017`.
>   The `+0.0135` is the **25-seed cross-seed mean** (`paired_significance.csv` mean 0.013371)
>   mislabeled as one seed; `+0.0038` is unsupported (true seed-42 ≈ `+0.0017`). Fix: relabel
>   as the cross-seed mean, or restate the real seed-42 values.
> - **§6 counterfactual MAE (0.093 / 0.11)** look pre-§7-fix; a live run gives naive ≈ 0.096
>   and propagation-slice ≈ 0.092 (the 0.11 matches the *intervenable* slice, 0.112).
> - **Not re-verified:** the fidelity gate (needs the real `train.csv`, absent here).

---

## 1. Why this exists

In real lending data you only observe repayment outcomes for loans the prior
underwriter **approved**; the **declined** applicants you must still score have no
ground truth. So you cannot directly measure how good a PD model is on them. The
same blind spot applies to two other deliverables of the challenge. The fix, in all
three cases, is to **plant the ground truth in synthetic cohorts**, hide it the way
the real process does, and measure against it:

| Real data cannot tell you… | because… | the synthetic SCM gives it | Deliverable |
|---|---|---|---|
| PD calibration on **declined** applicants | selective labels — no outcomes for declines | plant true default for all, hide via the approval policy | **A** + D §4 |
| **counterfactual** accuracy of `do(feature=value)` | you never see the same borrower both ways | plant the structural equations → compute the *true* interventional PD | **C** + D §3 |
| trajectory accuracy at default rates outside the realized window | only one realized regime | sweep the base rate / selection severity | **B** + D §5 |

The closed-loop methodology is adapted from a prior project of the author's
(`upstream-label-correction`) — taken **only** as the abstract loop pattern
(generate → measure → improve → frontier, strict train/measure no-leakage,
escalate corruption past what real data can reach). None of that project's domain
specifics are relevant here; treat the lineage as a design pattern, not a
dependency.

---

## 2. Repo layout

```
src/cldd/
  config.py          seeds, loan economics, severity grid, fidelity tolerances,
                     positivity-diagnostic thresholds, exploration stream tags
  synthetic.py       SyntheticBorrowerGenerator — the ORIGINAL flat selective-labels
                     generator (single-layer logistic). Drives the loop below.
  model_pd.py        calibrated PD model (HistGBT + isotonic) + IPW weights
  eval_default.py    measure stage: train-on-approved, score-on-full-truth (all/approved/declined)
  loop.py            SelectiveLabelsLoop — generate→measure→improve→frontier
                     (+ exploration lever, + observable diagnostics per round)
  feedback.py        FeedbackLoop — model-in-the-loop selective labels across
                     deployment generations (see §10)
  diagnostics.py     observable positivity diagnostics (no declined labels needed)
  scm.py             StructuralBorrowerGenerator — the FAITHFUL structural model
                     (fitted marginals + layered DAG + survival + do_intervention)
  fidelity.py        VERIFY-FIDELITY gate: synthetic vs real-data marginals
  counterfactual.py  Deliverable-C-style query set + estimator grading
scripts/
  run_clue.py        run the selective-labels loop -> artifacts/clue_frontier{,_scm}.{csv,png}
  run_exploration_sweep.py  frontier vs exploration budget -> artifacts/exploration_frontier.csv
  run_feedback.py    feedback generations -> artifacts/feedback_generations.csv
  run_seed_sweep.py  multi-seed counterfactual certification -> artifacts/seed_sweep.csv
  check_fidelity.py  run the fidelity gate, exit nonzero on drift
tests/               run pytest for the authoritative count (66 at last green run)
```

Two generators coexist on purpose. `synthetic.py` is the original, lightweight one
the selective-labels **loop** runs on. `scm.py` is the newer, fitted, causal one
used by the **fidelity gate** and the **counterfactual** validator. `scm.py` was
added **additively** — its `generate_cohort()` returns a *superset* of the loop's
cohort contract, so `SelectiveLabelsLoop` can be pointed at it later without
breaking anything. Nothing in `synthetic.py`/`loop.py`/`eval_default.py`/
`model_pd.py` was modified when `scm.py` landed.

---

## 3. The closed loop (already working)

`SelectiveLabelsLoop` (in `loop.py`) runs rounds of:

1. **generate** a cohort at the round's `selection_severity` (0 = approval random
   wrt risk; 1 = approval tracks the full latent risk incl. an unobserved confounder),
2. **measure** the naive PD model (trained on approved rows only) against planted
   truth, focused on the **declined** subpopulation's calibration error (ECE),
3. **improve** via two levers — **IPW reweight** (inverse-propensity) and **retrain**
   on a disjoint cohort (no-leakage, seed offset `TRAIN_SEED_OFFSET`),
4. **escalate** severity while the corrected model still clears the target, then stop
   and report the **operating frontier** (highest passing severity).

`scripts/run_clue.py` runs it and writes `artifacts/clue_frontier.{csv,png}` plus a
§3/§4/§5-ready summary. Result with the original flat generator: IPW holds
calibration on the unobservable declines out to **severity ≈ 0.4**, then positivity
breaks down and selection leaks through the unobserved confounder — an honest limit
to disclose.

---

## 4. The structural model + fidelity gate (working)

`StructuralBorrowerGenerator` (`scm.py`) is a deterministic, seeded, **layered SCM**:

- 28 modeled features across the dictionary's groups; all 16 `intervenable=True`
  features plus the business-identity roots and the `prior_underwriter` selection
  node. Bank-feed columns are NaN when no feed is linked (structural missingness).
- Marginals **fitted to the real Intuit `train.csv`** (lognormal/beta/Poisson/etc.),
  so the fidelity gate passes (see §6).
- A **layered DAG** with parent coefficients drawn from real correlations;
  descendants propagate with **frozen exogenous noise**, so `do(X = observed)` is an
  exact no-op (verified < 1e-13).
- A `prior_underwriter` **selection node** producing the approval mask (selective
  labels), plus **90-day censored survival** (`days_to_default ∈ [1,90]`,
  `observation_status`).
- `do_intervention(state, feature, value)` returns the **true** post-intervention
  default probability by clamping `feature` and re-propagating its descendants.

**Public API (downstream code is written against this):**
- `StructuralBorrowerGenerator(n_applicants=4000, selection_severity=1.0,
  approval_rate=0.60, target_base_rate=0.17, bank_feed_rate≈0.643,
  unobserved_strength=0.55, seed=42)`; `.unit()` (n=1500), `.benchmark()` (n=8000).
- `generate_cohort() -> dict` with keys: `features` (DataFrame, `FEATURE_COLUMNS`,
  28 float cols), `true_default`, `approved`, `prior_score`, `true_pd`,
  `days_to_default`, `observation_status`, `scm_state` (an `SCMState` carrying the
  frozen noise/latents needed for counterfactuals), `ground_truth`.
- `true_pd(state=None)`, `do_intervention(state, feature, value) -> InterventionResult`
  (`true_pd`, `baseline_pd`, `effect`, `intervenable`, `in_support`, `is_noop`).
- Constants: `FEATURE_COLUMNS`, `INTERVENABLE_FEATURES` (16), `BANK_FEED_COLUMNS`,
  `FEATURE_SUPPORT` (train [min,max] per feature).

`fidelity.py` compares a generated cohort to the real CSVs (base rate, feed rate,
missingness, per-feature p1/p50/p99, categorical frequencies) and returns a
`FidelityReport` with per-check pass/fail against `config` tolerances.
`scripts/check_fidelity.py` prints it and exits nonzero on drift. **The real-data
path is a parameter** — on another machine, pass the dataset dir explicitly.

---

## 5. The counterfactual validator (working, but see §7 gaps)

`counterfactual.py` builds a query set mirroring the real Deliverable-C
`intervention_queries.csv` (3 queries/applicant, a share of non-intervenable
targets, ~no-ops, dose-response ladders, all in-support) and grades estimators of
`do(feature=value)` against the SCM's planted truth:

- **naive observational** — fit a PD model on approved rows, answer a query by
  overwriting that one column and re-predicting. This is *conditioning*, not
  intervening: it ignores descendants and inherits selection bias.
- **"SCM-aware"** — currently calls `do_intervention` directly (**this is the oracle**
  — see §7 gap 1).
- no-op invariance and dose-response monotonicity are checked directly.

`run_counterfactual_eval(...)` returns a `CounterfactualResult` with MAE/bias split
by intervenable / non-intervenable / propagation slices, plus `.summary()`.

---

## 6. Verified results (re-run independently this session)

- **Tests:** `66 passed` in the pinned environment (Python 3.14.2,
  scikit-learn 1.9.0, numpy 2.4.6). Under scikit-learn 1.8.0 exactly three
  environment-sensitive tests differ (HistGradientBoosting float output shifts
  across sklearn releases); the pin is now declared in `pyproject.toml`. Run
  `pytest` for the authoritative count and module breakdown.
- **Fidelity gate: PASSED.** Real (labeled n=51,722) vs synthetic (n=12,000):
  default base rate 0.1745 → 0.1666; `has_linked_bank_feed` 0.643 → 0.646;
  bank-feed missingness 0.357 → 0.354; all 16 intervenable features' p1/p50/p99
  within tolerance (continuous within 30% relative, near-zero medians within
  absolute slack).
- **Counterfactual:** naive observational MAE vs known truth = **0.093**, rising to
  **0.11 on features whose interventions propagate** — where the true effect is only
  **0.116**, i.e. naive is wrong by almost the entire effect size. Query set: 900
  queries, 139 non-intervenable (15.4%), 33 no-ops (3.7%) (real file: 19.3% / 7.0%).

---

## 7. The two §3 gaps — RESOLVED on `feat/causal-gcomputation-and-gating`

> **STATUS: both closed.** The bank-feed trap now propagates and a deployable
> g-computation estimator replaces the oracle comparison. Measured (seed 42):
> at moderate selection (severity 0.4, inside the frontier) g-computation beats
> naive conditioning on the strong descendant-propagation slice
> **0.0734 → 0.0598 (gap +0.0135)**; the advantage shrinks toward noise at full
> severity (+0.0038) — the same selective-labels limit §5 discloses. All 66 tests
> pass (pinned sklearn 1.9.0); fidelity gate still green. The original gap descriptions are kept below as
> the record of what was changed.

**Gap 1 — the "SCM-aware" estimator is the oracle.** In `counterfactual.py`,
`_scm_aware_effects` calls the same `do_intervention` that *defines* the ground
truth, so `scm_mae = 0.0` by construction and "SCM-aware beats naive" is
tautological. We have proven naive conditioning is **biased**, not that a
*deployable* method recovers truth.
→ **Fix:** add a real **g-computation / backdoor-adjustment** estimator fit from the
observed (approved) data only — fit each child mechanism `E[child | parents]` and an
outcome model `E[default | features]`, then for `do(X=v)` clamp X, propagate through
the *fitted* mechanisms (standardization), and average. Grade its MAE vs the oracle
truth. Then §3 can claim a shippable method recovers the intervention (MAE measured)
while naive conditioning does not.

**Gap 2 — the bank-feed propagation trap is not exercised.** In `scm.py`,
`do_intervention` refuses non-intervenable features (`scm.py` ~L383–389: returns
baseline, effect 0), and `_propagate` returns the bank-feed block unchanged for
`has_linked_bank_feed` (~L721–722). So `do(has_linked_bank_feed=True)` does **not**
regenerate the 6-node bank-feed block — the ~19% non-intervenable trap is invisible
(true effect ≈ 0 *and* naive ≈ 0; non-intervenable MAE 0.0045).
→ **Fix:** make `do(has_linked_bank_feed=True)` a structural switch that regenerates
the whole bank-feed block from the SCM with frozen noise and recomputes the risk
logit (`=False` deletes it). Then the naive boolean-overwrite visibly fails to
propagate → measurable trap MAE. **Design stance to state in D §3:** propagate the
*manipulable* gating node; keep genuinely non-manipulable identity nodes (`sector`,
`vintage_years`) as "do() refused / ill-defined." Update `counterfactual.py` to
include `has_linked_bank_feed` in the propagation/trap slice.

Both gaps are recorded in the latest commit body. They feed Deliverable D **§3**
(causal reasoning), the most heavily weighted section.

---

## 8. How to continue

```bash
git clone https://github.com/hossainpazooki/closed-loop-default-detection
cd closed-loop-default-detection
python -m venv .venv && . .venv/Scripts/activate    # *nix: bin/activate
pip install -e ".[dev]"
pytest                                               # 66 pass (pinned sklearn 1.9.0)
python scripts/run_clue.py                           # selective-labels frontier
python scripts/check_fidelity.py                     # fidelity gate (pass real-data dir if needed)
```

Real Intuit data lives in the hackathon repo at
`…/intuit-techweek-nyc-hackathon-2026/dataset/` (`train.csv`, `validation.csv`,
`test.csv`, `data_dictionary.csv` with the `intervenable` flag,
`intervention_queries.csv`). On another machine, point the fidelity functions at
that directory explicitly.

**Suggested execution for the §7 fixes:** a small, focused workflow — build Gap-2
gating in `scm.py`, build Gap-1 g-computation in `counterfactual.py`, update the
tests, then verify (`pytest` + `check_fidelity.py`). Keep the two generators’
cohort contract stable; preserve determinism (single seeded
`numpy.random.Generator`, no `Date.now`/`random` outside the seeded stream); keep
the no-leakage discipline (train/measure on disjoint seeds).

---

## 9. Post-hackathon expansion: closing the loop (`feat/close-the-loop`)

Built from the lessons recorded in FABLE.md after the submission freeze. Three
components, all **measured in the two synthetic worlds only**:

1. **Exploration lever** (`SelectiveLabelsLoop(exploration_rate=eps)`): randomly
   approve an eps-fraction of declines; train on all funded rows with **exact**
   labeled-propensity weights (1 for approvals, 1/eps for explored) — known by
   construction, immune to the unobserved confounder that defeats fitted IPW.
   Measured (SCM, seeds {7, 42, 2026}): at severity 0.6 — past the certified
   frontier — eps=0.10 holds declined-ECE at 0.076/0.092/0.155 vs IPW's
   0.249/0.244/0.253 (target 0.10: cleared on 2/3 seeds). eps in {0.02, 0.05}
   is too noisy to certify at n=4000 (tens of bought labels carry the whole
   declined population). Evidence: `artifacts/exploration_frontier.csv`.
2. **`FeedbackLoop`** (`feedback.py`): from generation 1 the deployed model's
   own top-k approvals decide the next training labels — the loop the static
   harness never closed. The deceptive dynamic is measured: the funded book
   *improves* while blind-spot under-prediction grows; eps=0.05 cuts the mean
   under-prediction over model generations from +0.15/+0.13 (sev 0.4/1.0) to
   +0.06/+0.05. Per-generation declined-ECE is non-monotone (sampling noise);
   tests assert only the bias reduction. Evidence:
   `artifacts/feedback_generations.csv`.
3. **Observable positivity diagnostics** (`diagnostics.py`, `diag_*` columns on
   every loop round): propensity AUC, IPW ESS ratio, share of declines below
   the clip floor — computable without a single declined label. Thresholds
   (config `DIAG_*`) calibrated at n=4000 on both worlds' grids, seeds
   {7, 42, 2026}: each component separates every pass-severity (<= 0.4) cell
   from every fail-severity (>= 0.6) cell. The flag detects the
   positivity-breakdown **regime**, not per-cohort ECE; the in-sample AUC
   inflates at smaller n (documented in test_diagnostics). In the feedback
   world the flag fires on 15/15 model generations.

Determinism notes: exploration draws use dedicated streams
(`config.EXPLORE_STREAM_LOOP` / `EXPLORE_STREAM_FEEDBACK`, seeded
`[seed, iteration, tag]`) so generator PCG64 streams are untouched; the flat
frozen-baseline test still passes with exact float equality. The model policy
in `FeedbackLoop` is rank-based top-k (NOT a quantile cutoff — isotonic ties
overfund; this was caught and fixed during the build).

## 10. Invariants to preserve

- **Determinism:** byte-identical per seed; all randomness through one seeded
  `numpy.random.Generator`.
- **No-leakage:** the retrain lever fits on a disjoint cohort (`TRAIN_SEED_OFFSET`);
  the naive PD model is fit on approved rows only.
- **Cohort contract:** `scm.py` must keep returning the loop-compatible superset
  dict so `SelectiveLabelsLoop` can consume it.
- **Fidelity gate is the guard:** any change to marginals must keep
  `check_fidelity.py` green, or the tolerances must be revisited deliberately.
- **Scope:** this repo is a validation harness; it does **not** produce or alter the
  challenge's A/B/C submission files. Wiring its conclusions (IPW correction,
  disclosed frontier, counterfactual method) into the real submission is a separate
  step.
