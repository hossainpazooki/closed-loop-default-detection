# How the closed loop works

"Closed loop" is the **generate → measure → improve → regenerate** cycle, escalating each
round until the detector fails.

| Stage | Module | What happens |
|---|---|---|
| **Generate** | `cldd/synthetic.py` (or `cldd/scm.py`) | build a cohort at `selection_severity ∈ [0,1]` (0 = approval random w.r.t. risk, 1 = approval tracks full latent risk incl. an unobserved confounder) |
| **Measure** | `cldd/eval_default.py` | train the PD model on approved rows only; score against planted truth on the **declined** subpopulation (ECE is the headline metric) |
| **Improve** | `cldd/loop.py` + `cldd/correctors.py` | apply the pluggable correction levers — **IPW reweight**, **retrain** on a disjoint no-leakage cohort, **exploration** (buy labels) |
| **Regenerate / frontier** | `cldd/loop.py` | if the corrected model still clears the target, raise severity; otherwise stop and report the frontier |

Because part of the approval policy runs through an **unobserved confounder**, observational
corrections (like inverse-propensity weighting) degrade as severity rises — so the frontier
is a real, defensible limit, not an artifact.

## The two attached mechanisms

Two mechanisms hang off the loop — one observable without any declined-row label, one that
simulates the deployment feedback dynamic:

- **Positivity diagnostics** (`cldd.diagnostics`) fire from observables alone — propensity
  AUC, IPW effective-sample-size ratio, clip-floor share — so a regime/drift alarm needs
  **no** declined-row label.
- **`FeedbackLoop`** (`cldd.feedback`) simulates the deployment dynamic where the model's own
  approvals shape the next generation's training labels.

## Pricing the frontier: the EMP layer (`cldd.emp`)

ECE says *whether* the detector is wrong on the declines; it never says what being wrong
**costs**. `cldd.emp` adds an expected-maximum-profit axis on top of the same in-process
scores the loop already measures.

**It is a reporting axis, not a control input.** `control_metric`, `passed`, severity
escalation and the frontier are all still keyed on declined-subpopulation ECE — the loop makes
exactly the same decisions it made in v1 (enforced: every v1 column of the committed frontier
CSVs is byte-identical after the v2 wiring; the EMP columns are strictly appended).

| Entry point | Parameters | Applies to |
|---|---|---|
| `empc_literature` | the Verbraken et al. (2014) EMPC prior from `config.py` (`EMPC_P0/P1/ROI`) — closed form over the ROC convex hull, Eqs. 13/15 | every cohort |
| `emp_harness` | this harness's own loan economics (`TERM_DAYS`, `APR`, `ORIGINATION_FEE_RATE`) plus the **planted** per-row default day | SCM cohorts only — returns `None` on flat cohorts, which plant no timing |

Both consume the score as a **ranking only** (invariant to any strictly monotone transform —
test-enforced), both report profit per applicant as a fraction of mean exposure so the two
columns are comparable, and both are pure-numpy with zero RNG.

The two variants **disagree by design, and the disagreement is a result**: the literature prior
assumes a 26.44% ROI where a 60-day daily-ACH loan returns 8.75%, and puts 55% of defaults at
full recovery where this harness plants ~1%. See the README's *Pricing the frontier* section
for the measured numbers and the four reading caveats — most importantly that `emp_h` rests on
**planted, unfitted** default timing (a verified experiment, not a verified result) and that
post-term "day-90" defaults are priced by a stated imputation, not measured truth.

Exploration is priced on the same economics: `RoundResult.exploration_cost` is the net dollar
cost of the labels the lever bought that round (positive = the budget lost money).

## Pricing the feedback loop: arms, pairing, units (v3)

v3 decomposes the closed loop's realized cost with **three arms** run on identical cohorts
(same generator seeds within a (seed, severity) cell, so every contrast is a within-seed
paired series): *treatment* is today's `FeedbackLoop` (model policy, retrain each
generation); *frozen* (`retrain=False`) deploys the generation-0 model forever, isolating
feedback accumulation — exploration starts at generation 1 there, and explored rows fund
but never train; *prior* (`policy_mode="prior"`) funds via the cohort's own prior-policy
column, the iid noise floor. The unit everywhere is `realized_book_profit`: total realized
P&L of the funded rows divided by full-cohort exposure (n_applicants x mean requested
amount) — the full-cohort denominator keeps arms with different funded counts comparable.
Day-90 tail defaulters are imputed at the **cohort's** mean in-term loss fraction (a
planted, funding-invariant basis — required for the H4 identity, spec Rev 2.1/2.2).
Statistics are paired over generations 1..11: exact sign test primary, Wilcoxon
supporting, Holm across H1–H3, and a pre-registered noise floor (the prior arm's own
generation-to-generation variability). H4 is an *integrity control*, not a hypothesis:
frozen-arm eps difference must equal the explored slice's own P&L exactly, verifying the
flags freeze what they claim to freeze.

## Intervening on the confounder (v4)

Everything above measures the worlds at their default unobserved-confounder strength —
which leaves the causal story ("one cause explains both failure modes") a reading, not a
result. v4 turns that reading into an intervention: `generator_kwargs` on the loop and
`unobserved_strength` on `run_counterfactual_eval` sweep the confounder's strength as an
explicit axis over a 6-point grid in both worlds, against four confirmatory hypotheses
pre-registered with Holm correction, effect floors, and a falsification statement written
before the data (spec `2026-07-29-cldd-v4-option-a-surface-design.md`, Rev 1.2).

The pre-registered attack fired. All four hypotheses came back not confirmed — the
frontier wall stands with the confounder switched off, and the counterfactual gap moves
opposite the predicted direction — so the one-cause attribution is withdrawn, as measured.
The wall does move at maximum strength, observed post-hoc: a hypothesis for a future
pre-registration, not a confirmation. Every figure behind this paragraph is quoted and
registered in the [README's v4 section](https://github.com/hossainpazooki/closed-loop-default-detection#the-cause-tested-by-intervention-v4)
and recomputes via `scripts/surface_stats.py`, which fail-closes on missing cells and
enforces a byte-identity embed gate before reporting anything.

## Replicating the strength-1.0 move

The v4 surface showed the frontier moving only at full confounder strength, and that was
read off the surface after the data was in. It was therefore re-run as its own experiment,
on seeds no committed artifact had consumed, and pre-registered by digest (see
`PREREGISTRATION.md`; the specification is held outside the repository). The driver is
the v4 surface child
with one inserted block, the four overlap-diagnostic columns the loop already computes.

The primary outcome is continuous: the declined-pool calibration error of the loop's
control lever at severity 0.4, contrasted between strength 0 and strength 1.0 on the same
seed. Its floor is the larger of two quantities measured inside the experiment: the
distance from the strength-0 median to the calibration target, and the noise in the same
contrast at severity 0, where selection is random and strength cannot act through it. The
frontier is a secondary family, because a grid-quantized outcome can only clear a one-step
floor by sitting on it.

Both worlds replicated on the primary outcome, and both frontier hypotheses were confirmed
on their floor. The dose response, against strength 0 at severity 0.4:

| Strength 0 → | 0.2 | 0.4 | 0.55 | 0.7 | 1.0 |
|---|---|---|---|---|---|
| Flat: median change | +0.0042 | +0.0131 | +0.0273 | +0.0265 | +0.0515 |
| Flat: seeds rising, of 25 | 15 | 19 | 22 | 24 | 25 |
| SCM: median change | −0.0049 | −0.0006 | +0.0040 | +0.0119 | +0.0201 |
| SCM: seeds rising, of 25 | 10 | 12 | 17 | 17 | 20 |

The frontier, per cell:

| Strength | 0.0 | 0.2 | 0.4 | 0.55 | 0.7 | 1.0 |
|---|---|---|---|---|---|---|
| Flat: median frontier | 0.4 | 0.4 | 0.4 | 0.4 | 0.4 | 0.2 |
| Flat: seeds at 0.2 or below, of 25 | 1 | 0 | 1 | 8 | 10 | 20 |
| SCM: median frontier | 0.4 | 0.4 | 0.4 | 0.4 | 0.2 | 0.2 |
| SCM: seeds at 0.2 or below, of 25 | 8 | 4 | 7 | 9 | 16 | 19 |

Two descriptive reads of the overlap diagnostics at strength 0 came with it. Across
severities the abstention flag fired at the failing severity on most runs, which means the
pre-stated reading rule does not withdraw the overlap explanation. It does not confirm it
either, because the flag and the failure both follow severity. Within severity 0.4 the
diagnostics do not separate failing runs from passing ones:

| World | Failing runs | Passing runs | Median propensity AUC, failing vs passing | Spearman of AUC against calibration error |
|---|---|---|---|---|
| Flat | 1 | 24 | 0.826 vs 0.823 | +0.17 (p = 0.42) |
| SCM | 8 | 17 | 0.834 vs 0.834 | -0.05 (p = 0.82) |

So the confounder does not build the wall, and at full strength it moves it. What builds
the wall with the confounder off is untested by intervention. Every figure quoted in the
README for this experiment is registered in the doc-number gate and recomputes via
`scripts/strength_replication_stats.py`.

## Why it is useful

- **Earlier, broader detection.** The loop scores and *calibrates* default risk on the
  **declined** applicants real data never labels — not just the approved book — so blind
  spots surface before they cost anything.
- **Improvement from observed outcomes (within the harness).** Each round applies the
  correction levers and re-measures; `FeedbackLoop` additionally simulates the deployment
  dynamic where the model's own approvals shape the next generation's training labels.
- **Drift and performance visibility.** Observable positivity diagnostics fire *without any
  declined-row label*, and the marginal-fidelity gate guards the synthetic world's univariate
  marginals against real-data drift.
- **A clear, checked feedback path.** Every correction is graded against planted ground truth,
  so the loop reports a defensible **operating frontier** instead of an unverifiable score.

## What this loop is — and isn't

This is a **synthetic validation harness**, not a live production pipeline. The "retrain"
lever and the feedback dynamic are **deterministic, seeded simulations** run inside the
harness — **the system does not retrain automatically and does not act on live data or real
lending decisions.** A deployed system's "decision → observed outcome" path is modeled here
by the synthetic approval policy and, for the model-as-policy dynamic, by `FeedbackLoop`.
Wiring any of this into a production system is a separate, manual step.

## Outputs

All drivers write to `artifacts/`:

| File | Produced by | Notes |
|---|---|---|
| `loop_frontier.{csv,png}` / `loop_frontier_scm.{csv,png}` | `run_loop.py` | frontier table + plot (+ EMP columns / EMP panel) |
| `frontier_sweep.csv` | `run_frontier_sweep.py` | frontier distribution across the 25-seed set |
| `seed_sweep.csv` | `run_seed_sweep.py` | 5-seed counterfactual certification (committed) |
| `seed_sweep_25.csv`, `severity_curve.csv` | committed evidence | 25-seed sweep + collapse curve |
| `exploration_frontier.csv` | `run_exploration_sweep.py` | frontier vs exploration budget |
| `reject_inference_frontier.csv` | `run_reject_inference.py` | reject-inference levers vs frontier |
| `feedback_generations.csv` | `run_feedback.py` | per-generation feedback metrics |
| `paired_significance.csv` | `paired_significance.py` | paired test on the 25-seed gap |

`artifacts/` is gitignored **except** an allowlist of CSVs (and the sweep driver) committed so
the figures quoted in `docs/assessment.md` are recomputable from source. PNGs are not committed.

## Repository structure

```
.
├── src/cldd/                 # the package (import as `cldd`)
│   ├── config.py             # seeds, loan economics, severity grid, diagnostic thresholds
│   ├── synthetic.py          # SyntheticBorrowerGenerator — flat world (drives the loop)
│   ├── scm.py                # StructuralBorrowerGenerator — fitted SCM world
│   ├── model_pd.py           # calibrated PD model (HistGBT + isotonic) + sklearn estimator + IPW weights
│   ├── eval_default.py       # measure: train-on-approved / score-on-truth
│   ├── emp.py                # price: expected maximum profit (literature EMPC + harness-derived)
│   ├── loop.py               # SelectiveLabelsLoop — improve / frontier
│   ├── correctors.py         # Corrector ABC + 4 pluggable levers (naive/reweight/retrain/explore)
│   ├── reject_inference.py   # 4 classic reject-inference methods as Correctors
│   ├── feedback.py           # FeedbackLoop — model-in-the-loop selective labels
│   ├── diagnostics.py        # observable positivity diagnostics
│   ├── fidelity.py           # fidelity gate + FidelityReport (.get_score / .get_details)
│   └── counterfactual.py     # counterfactual query set + estimator grading
├── scripts/                  # runnable drivers (each adds src/ to sys.path, no install needed)
├── tests/                    # pytest suite (149 tests; 6 marked `pinned`)
├── docs/                     # this Sphinx site (sphinx-build -W; RTD-ready) + assessment.md, the dated article
├── examples/                 # runnable quickstart (synthetic-only) + its README
├── CONTRIBUTING.md           # dev setup + how to add a correction lever
├── pyproject.toml            # package metadata + dependency ranges (provenance pins in requirements-dev.txt)
└── requirements-dev.txt      # pinned dev environment (the provenance pins)
```

## Development invariants

- **Determinism is an invariant.** Every run is byte-identical per seed; all randomness goes
  through seeded `numpy.random.Generator` streams, and levers use dedicated RNG stream tags
  (`config.EXPLORE_STREAM_*`) so they can't shift a generator's stream. (A custom `Corrector`
  must likewise seed from `ctx`, not a global RNG.)
- **No-leakage discipline.** The retrain lever fits on a disjoint cohort
  (`RANDOM_SEED + TRAIN_SEED_OFFSET + iteration`); the naive PD model is fit on approved rows
  only. Don't collapse these.
- **Two generators, one contract.** `scm.py` returns a *superset* of the loop's cohort dict, so
  `SelectiveLabelsLoop` runs on either world. Keep that contract stable.
- **The marginal-fidelity gate is the guard.** It checks univariate marginals only (not the
  joint/causal structure), so any change to SCM marginals must keep `check_fidelity.py` green,
  or the tolerances must be revisited deliberately.
- **`src/` layout.** Scripts inject `src/` onto `sys.path`, so they run without installing, but
  `pip install -e .` is recommended for tests and imports.
