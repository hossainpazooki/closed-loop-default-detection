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
| `loop_frontier.{csv,png}` / `loop_frontier_scm.{csv,png}` | `run_loop.py` | frontier table + plot |
| `seed_sweep.csv` | `run_seed_sweep.py` | 5-seed counterfactual certification (committed) |
| `seed_sweep_25.csv`, `severity_curve.csv` | committed evidence | 25-seed sweep + collapse curve |
| `exploration_frontier.csv` | `run_exploration_sweep.py` | frontier vs exploration budget |
| `reject_inference_frontier.csv` | `run_reject_inference.py` | reject-inference levers vs frontier |
| `feedback_generations.csv` | `run_feedback.py` | per-generation feedback metrics |
| `paired_significance.csv` | `paired_significance.py` | paired test on the 25-seed gap |

`artifacts/` is gitignored **except** an allowlist of CSVs (and the sweep driver) committed so
the figures quoted in `FABLE.md` are recomputable from source. PNGs are not committed.

## Repository structure

```
.
├── src/cldd/                 # the package (import as `cldd`)
│   ├── config.py             # seeds, loan economics, severity grid, diagnostic thresholds
│   ├── synthetic.py          # SyntheticBorrowerGenerator — flat world (drives the loop)
│   ├── scm.py                # StructuralBorrowerGenerator — fitted SCM world
│   ├── model_pd.py           # calibrated PD model (HistGBT + isotonic) + sklearn estimator + IPW weights
│   ├── eval_default.py       # measure: train-on-approved / score-on-truth
│   ├── loop.py               # SelectiveLabelsLoop — improve / frontier
│   ├── correctors.py         # Corrector ABC + 4 pluggable levers (naive/reweight/retrain/explore)
│   ├── reject_inference.py   # 4 classic reject-inference methods as Correctors
│   ├── feedback.py           # FeedbackLoop — model-in-the-loop selective labels
│   ├── diagnostics.py        # observable positivity diagnostics
│   ├── fidelity.py           # fidelity gate + FidelityReport (.get_score / .get_details)
│   └── counterfactual.py     # counterfactual query set + estimator grading
├── scripts/                  # runnable drivers (each adds src/ to sys.path, no install needed)
├── tests/                    # pytest suite (123 tests; 6 marked `pinned`)
├── docs/                     # this Sphinx site (builds with sphinx-build -W; RTD-ready)
├── examples/                 # runnable quickstart (synthetic-only) + its README
├── CONTRIBUTING.md           # dev setup + how to add a correction lever
├── pyproject.toml            # package metadata + dependency ranges (provenance pins in requirements-dev.txt)
├── requirements-dev.txt      # pinned dev environment (the provenance pins)
├── FABLE.md                  # the accompanying article: independent results & methodology assessment
└── SESSION_HANDOFF.md        # architecture / handoff notes
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
