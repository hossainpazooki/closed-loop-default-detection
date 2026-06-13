# closed-loop-default-detection

A **CLUE-style closed loop** that measures — and stress-tests — probability-of-default
(PD) modeling under **selective labels**, the central difficulty of the Intuit TechWeek
SMB Underwriting Challenge.

## The problem, in one paragraph

In real lending data you only observe repayment outcomes for loans the prior underwriter
**approved**. The applicants it **declined** are exactly the ones you must still score — and
their ground truth does not exist, so you can't measure how good your PD model is on them.
This harness sidesteps that the way [CLUE](../upstream-label-correction) sidesteps unmeasurable
label error: it **plants** the ground truth in synthetic cohorts, **hides** it through a
realistic approval policy, measures the model on the unobservable declines, then **escalates**
the selection severity until the model breaks — reporting the **operating frontier**, the
honest limit you'd disclose to a regulator.

## The loop

**generate → measure → improve → regenerate**, escalating until the detector breaks:

1. **Generate** (`cldd/synthetic.py`) — a synthetic SMB cohort with a planted true
   `default_flag` for *every* applicant. A prior-underwriter policy funds the lowest-risk
   fraction; `selection_severity ∈ [0,1]` sets how tightly approval tracks true risk
   (0 = random, 1 = approval tracks the full latent risk **including an unobserved
   confounder**). Outcomes are observable only for approved rows — selective labels by construction.
2. **Measure** (`cldd/eval_default.py`) — train the PD model on approved rows only, score it
   against planted truth on the **declined** subpopulation. Declined calibration error (ECE)
   is the headline metric.
3. **Improve** (`cldd/loop.py`) — three levers:
   - **IPW reweight** — inverse-propensity reweighting of approved training rows to undo
     prior-approval selection bias.
   - **Retrain** — refit on a **disjoint** train cohort (offset seed), score on the held-out
     measure cohort: an honest, no-leakage metric.
   - **Exploration** (`exploration_rate=eps`) — randomly approve an eps-fraction of declines
     to *buy* labels, then train with **exact** labeled-propensity weights (approvals 1,
     explored declines 1/eps). Those weights are known by construction, not fitted, so the
     unobserved confounder can't distort them — the only lever that buys *identification*
     rather than reweighting. Its cost (defaults among explored loans) is explicit and observable.
4. **Regenerate / frontier** — if the corrected model still clears the target on declines, raise
   the severity and probe a harder regime; otherwise stop and report the **frontier** (highest
   passing severity).

Because part of the selection runs through an **unobserved confounder**, IPW (which sees only
observed features) corrects less and less as severity rises — so the frontier is real.

## What it found

The headline results and the full independent assessment live in **[`FABLE.md`](FABLE.md)**.
In short:

- **Operating frontier ≈ severity 0.4.** IPW holds calibrated PD on the unobservable declines
  out to severity 0.4; past it, positivity breaks and the unobserved confounder leaks through.
- **A deployable g-computation estimator beats naive conditioning — inside the frontier.** On
  the slice where interventions propagate, the MAE gap is **+0.0134 ± 0.0085 across 25 seeds,
  positive on 24/25** (~13.5% relative). Past the frontier the advantage collapses to negligible.
- **Both limits share one cause.** The calibration frontier breaks and the counterfactual
  advantage collapses at the *same* severity, for the same reason — selection on an unobserved
  confounder. That single mechanism, measured two independent ways, is the result worth telling.

The win is real but **small and honestly far from full recovery** — `FABLE.md` states the
magnitude, the bias trade-off, and what *not* to claim.

## Closing the loop: feedback, exploration, observable diagnostics

The static loop above corrects against a **fixed** prior policy. The post-hackathon expansion
(rationale in `FABLE.md`) closes it for real with three additions, all **measured in the two
synthetic worlds only**:

**`cldd/feedback.py` — the model becomes the policy.** From generation 1 the *deployed model's*
own top-k approvals decide which outcomes the next model trains on. This reproduces the deceptive
real-world dynamic: the funded book *improves* (gen-1 default rate 0.076 → 0.047) while the
model's under-prediction on its own declines roughly **doubles** — everything a lender observes
looks fine while the blind spot grows. A 5% exploration budget cuts the mean blind-spot
under-prediction over generations from +0.15/+0.13 to +0.06/+0.05 and declined-ECE from
0.166/0.134 to 0.118/0.107 (seeds {7,42,2026} × severities {0.4,1.0}). Per-generation ECE is
noisy/non-monotone, so tests assert only the bias reduction. → `artifacts/feedback_generations.csv`.

**`cldd/diagnostics.py` — a positivity alarm that needs no declined labels.** Propensity
separability (AUC), IPW effective-sample-size ratio, and the share of declines below the
propensity clip floor — all computable on observed data alone. Calibrated on both worlds'
severity grids (seeds {7,42,2026}), each component separates every pass-severity (≤ 0.4) cell
from every fail-severity (≥ 0.6) cell. It is a **regime detector, not a per-cohort ECE
predictor** (one flat seed missed the ECE target at 0.4 with healthy diagnostics). In the
feedback world it fires from generation 1. → `diag_*` columns on every loop round.

**Exploration extends the frontier where nothing observational works.** At severity 0.6 — past
the certified frontier, where IPW is defeated by the unobserved confounder — a 10% exploration
budget holds declined-ECE at 0.076 / 0.092 / 0.155 (seeds {7,42,2026}) vs IPW's
0.249 / 0.244 / 0.253, clearing the 0.10 target on 2/3 seeds (~150–170 bought labels per round,
explored-loan default rates 2–3× the funded book). Budgets of 2–5% are too noisy to certify at
n=4000. → `artifacts/exploration_frontier.csv`.

> **Status / honesty.** All three are measured in this harness's two synthetic worlds; the
> diagnostics thresholds are a **proposal** for real-data monitoring, validated nowhere else
> yet. The in-sample propensity-separability AUC inflates at smaller n (documented in
> `test_diagnostics`), so the flag is calibrated at n=4000 and is a regime detector, not a
> per-cohort ECE predictor.

## Lineage: CLUE → this repo

The closed-loop *pattern* is borrowed from a prior project ([`upstream-label-correction`](../upstream-label-correction)),
taken only as the abstract loop shape — none of its domain specifics carry over.

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

Two generators coexist on purpose: `synthetic.py` (the lightweight flat world the loop runs on)
and `scm.py` (the fitted, causal world used by the fidelity gate and the counterfactual
validator). `scm.py` returns a superset of the loop's cohort contract, so the loop can run on
either.

```
src/cldd/
  config.py         seeds, loan economics, severity grid, target metric, diagnostic thresholds
  synthetic.py      SyntheticBorrowerGenerator   — flat selective-labels world (drives the loop)
  scm.py            StructuralBorrowerGenerator  — fitted SCM world (fidelity + counterfactuals)
  model_pd.py       calibrated PD model (HistGBT + isotonic) + IPW weights
  eval_default.py   measure: train-on-approved / score-on-truth (all/approved/declined)
  loop.py           SelectiveLabelsLoop          — improve / frontier (+ exploration + diagnostics)
  feedback.py       FeedbackLoop                 — model-in-the-loop selective labels over generations
  diagnostics.py    observable positivity diagnostics (no declined labels needed)
  fidelity.py       VERIFY-FIDELITY gate vs the real-data marginals
  counterfactual.py Deliverable-C query set + estimator grading (naive vs g-computation)
scripts/
  run_clue.py               run the loop          -> artifacts/clue_frontier{,_scm}.{csv,png}
  run_exploration_sweep.py  frontier vs budget    -> artifacts/exploration_frontier.csv
  run_feedback.py           feedback generations  -> artifacts/feedback_generations.csv
  run_seed_sweep.py         multi-seed certification -> artifacts/seed_sweep.csv
  paired_significance.py    paired test on the sweep -> artifacts/paired_significance.csv
  check_fidelity.py         fidelity gate, exit nonzero on drift
tests/   determinism, selection bias, IPW recovery, no-leakage, frontier,
         exploration, feedback, diagnostics, fidelity, counterfactual
```

## Quick start

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -e ".[dev]"                            # pins scikit-learn 1.9.0 / numpy 2.4.6

pytest                                             # 66/66
python scripts/run_clue.py                         # frontier table + plot in artifacts/
```

`run_clue.py` writes `artifacts/clue_frontier.{csv,png}` and prints a summary written for the
challenge's Deliverable D (§3 causal reasoning, §4 calibration, §5 limitations).

**On exact reproduction:** HistGradientBoosting's float output shifts across scikit-learn
releases, so the committed numbers are pinned to **scikit-learn 1.9.0 / numpy 2.4.6** (Python
3.14.2). On a different sklearn the last decimals move and 3 environment-sensitive tests differ —
the pin keeps "tests green / numbers reproduce" deterministic. See `FABLE.md` §8.

## Scope

Standalone and self-contained: it runs on synthetic data only and imports nothing from the
hackathon submission repo. It is a **validation harness** — it does not produce or alter the
challenge's A/B/C submission files. Wiring its conclusions (the IPW correction, the disclosed
frontier, the g-computation method) into the real submission is a separate step.
