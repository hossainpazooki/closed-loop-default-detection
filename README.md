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
3. **Improve** (`cldd/loop.py`) — two levers:
   - **IPW reweight** — inverse-propensity reweighting of approved training rows
     to undo prior-approval selection bias.
   - **Retrain** — refit on a **disjoint** train cohort (offset seed) and score on
     the held-out measure cohort: an honest, no-leakage metric.
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

## Layout

```
src/cldd/
  config.py        seeds, loan economics, severity grid, target metric
  synthetic.py     SyntheticBorrowerGenerator        (generate)
  model_pd.py      calibrated PD model + IPW weights
  eval_default.py  train-on-approved / score-on-truth (measure)
  loop.py          SelectiveLabelsLoop               (improve / frontier)
scripts/
  run_clue.py      run the loop -> artifacts/clue_frontier.{csv,png} + summary
tests/             determinism, selection bias, IPW recovery, no-leakage, frontier
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
