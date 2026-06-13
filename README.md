# closed-loop-default-detection

A **CLUE-style closed loop** that measures — and stress-tests — probability-of-default
(PD) modeling under **selective labels**, the central difficulty of the Intuit
TechWeek SMB Underwriting Challenge.

In real lending data you only observe repayment outcomes for loans the prior
underwriter **approved**; the applicants it **declined** are exactly the ones you
must still score, and their ground truth does not exist. So you cannot measure how
good your PD model is on them. This harness sidesteps that the way
[CLUE](../upstream-label-correction) sidesteps unmeasurable label error: it plants
the ground truth in **synthetic** cohorts, hides it through a realistic approval
policy, and measures the model on the unobservable declines — then escalates the
selection severity to find the model's **operating frontier**.

## The loop

**generate → measure → improve → regenerate**, escalating until the detector breaks:

1. **Generate** (`cldd/synthetic.py`) — a synthetic SMB applicant cohort with a
   planted true `default_flag` for *every* applicant. A prior-underwriter policy
   funds the lowest-risk fraction; `selection_severity ∈ [0,1]` controls how
   tightly approval tracks true risk (0 = random, 1 = approval tracks the full
   latent risk **including an unobserved confounder**). Outcomes are observable
   only for the approved rows — selective labels by construction.
2. **Measure** (`cldd/eval_default.py`) — train the PD model on the approved rows
   only, score it against the planted truth on the **declined** subpopulation
   (AUC, Brier, ECE, F1). Declined calibration error is the headline metric.
3. **Improve** (`cldd/loop.py`) — three levers:
   - **IPW reweight** — inverse-propensity reweighting of approved training rows
     to undo prior-approval selection bias.
   - **Retrain** — refit on a **disjoint** train cohort (offset seed) and score on
     the held-out measure cohort: an honest, no-leakage metric.
   - **Exploration** (`exploration_rate=eps`) — randomly approve an eps-fraction
     of the declines to *buy* labels. Training then uses **exact**
     labeled-propensity weights (approvals 1, explored declines 1/eps) — known by
     construction, not fitted, so the unobserved confounder cannot distort them.
     The only lever that buys identification rather than reweighting; its cost
     (defaults among explored loans) is explicit and observable.
4. **Regenerate / frontier** — if the corrected model still clears the target
   calibration on declines, raise the severity and probe a harder regime;
   otherwise stop and report the **frontier** (highest passing severity).

Because part of the selection runs through an **unobserved confounder**, IPW (which
sees only observed features) corrects less and less as severity rises — so the
frontier is real, and it is exactly the honest limit you'd disclose to a regulator.

## CLUE → this repo

| CLUE (`upstream-label-correction`) | This repo |
|---|---|
| Synthetic multi-omics cohort | Synthetic SMB applicant cohort |
| `mislabel_fraction` corruption | `selection_severity` (label-hiding aggressiveness) |
| Planted `mislabeled_samples` | Planted true `default_flag` for **all** applicants |
| Cross-omics distance detector | Calibrated PD model |
| Detect mislabels (F1) | Detect defaulters + calibrate PD **on declines** |
| `improve_mode` threshold/retrain/both | `improve_mode` reweight/retrain/both |
| `train_seed_offset` no-leakage | Same — disjoint train cohort |
| Operating frontier (max corruption passing) | Max selection severity passing |

## Closing the loop: feedback, exploration, and observable diagnostics

The static loop above measures correction against a **fixed** prior policy. The
post-hackathon expansion (lessons recorded in `FABLE.md`) closes it for real:

- **`cldd/feedback.py` — `FeedbackLoop`.** From generation 1 the *deployed
  model's own approvals* decide which outcomes the next model trains on. A
  deterministic model policy (fund the top-k safest) makes selection a function
  of the features, so funded/declined overlap is gone **by construction**.
  Measured (SCM world, severity 0.4, seed 42): the generation-1 funded book
  *improves* (default rate 0.076 → 0.047) while the model's under-prediction on
  its own declines roughly doubles — the deceptive dynamic where everything a
  real lender observes looks fine. Across seeds {7, 42, 2026} x severities
  {0.4, 1.0}, a 5% exploration budget cuts the mean blind-spot under-prediction
  over model generations from +0.15/+0.13 to +0.06/+0.05 and the mean
  declined-ECE from 0.166/0.134 to 0.118/0.107 — but per-generation ECE is
  noisy enough to be non-monotone, so only the bias reduction is asserted in
  tests. Evidence: `artifacts/feedback_generations.csv`
  (`scripts/run_feedback.py`).
- **`cldd/diagnostics.py` — observable positivity diagnostics.** Propensity
  separability (AUC), IPW effective-sample-size ratio, and the share of declines
  below the propensity clip floor — none needs a declined-row label. Calibrated
  on both worlds' severity grids (seeds {7, 42, 2026}): each component
  individually separates every pass-severity (≤ 0.4) from every fail-severity
  (≥ 0.6) cell, so the flag detects the positivity-breakdown **regime** the
  hidden ECE frontier lives in (it is *not* a per-cohort ECE predictor — one
  flat seed missed the ECE target at severity 0.4 with healthy diagnostics).
  In the feedback world the flag fires from generation 1 — the model-as-policy
  regime is instantly visible. Computed on every loop round (`diag_*` columns).
- **Exploration extends the frontier where nothing observational works.**
  At severity 0.6 — past the certified frontier, where IPW is defeated by the
  unobserved confounder — a 10% exploration budget holds declined-ECE at
  0.076 / 0.092 / 0.155 across seeds {7, 42, 2026} vs IPW's 0.249 / 0.244 / 0.253,
  clearing the 0.10 certification target on 2/3 seeds (~150–170 bought labels
  per round, explored-loan default rates 2–3× the funded book). Budgets of 2–5%
  are too noisy to certify at n=4000. Evidence:
  `artifacts/exploration_frontier.csv` (`scripts/run_exploration_sweep.py`).

Status: all three are **measured in the two synthetic worlds** of this harness;
the diagnostics thresholds are a *proposal* for real-data monitoring, validated
nowhere else yet — and because the in-sample propensity-separability AUC inflates
at smaller n (documented in `test_diagnostics`), the flag is calibrated at n=4000
and is a regime detector, not a per-cohort ECE predictor.

## Layout

```
src/cldd/
  config.py        seeds, loan economics, severity grid, target metric, diag thresholds
  synthetic.py     SyntheticBorrowerGenerator        (generate, flat world)
  scm.py           StructuralBorrowerGenerator       (generate, fitted SCM world)
  model_pd.py      calibrated PD model + IPW weights
  eval_default.py  train-on-approved / score-on-truth (measure)
  loop.py          SelectiveLabelsLoop               (improve / frontier)
  feedback.py      FeedbackLoop: model-in-the-loop selective labels across generations
  diagnostics.py   observable positivity diagnostics (no declined labels needed)
  fidelity.py      VERIFY-FIDELITY gate vs the real-data marginals
  counterfactual.py Deliverable-C-style query set + estimator grading
scripts/
  run_clue.py             run the loop -> artifacts/clue_frontier{,_scm}.{csv,png}
  run_exploration_sweep.py  frontier vs exploration budget -> artifacts/exploration_frontier.csv
  run_feedback.py         feedback generations -> artifacts/feedback_generations.csv
  run_seed_sweep.py       multi-seed counterfactual certification -> artifacts/seed_sweep.csv
  check_fidelity.py       fidelity gate, exit nonzero on drift
tests/             determinism, selection bias, IPW recovery, no-leakage, frontier,
                   exploration, feedback, diagnostics, fidelity, counterfactual
```

## Quick start

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -e ".[dev]"

pytest                      # run the test suite
python scripts/run_clue.py  # build the frontier table + plot in artifacts/
```

`scripts/run_clue.py` writes `artifacts/clue_frontier.csv` and
`artifacts/clue_frontier.png` and prints a short summary written for the SMB
challenge's Deliverable D writeup (§3 causal reasoning, §4 calibration, §5
limitations).

## Scope

Standalone and self-contained — it runs on synthetic data only and imports nothing
from the hackathon submission repo. It is a *validation harness*: it does not
produce or alter the challenge's A/B/C submission files. Wiring its conclusions
(the IPW correction, the disclosed frontier) into the real submission is a separate
step.
