# FABLE.md — Updated Methodology & Results Assessment

> Independent review of `closed-loop-default-detection` after PR #1
> (`feat/causal-gcomputation-and-gating`, merged 2026-06-06).
> All numbers below were **re-verified by re-running the code on 2026-06-10**,
> not copied from commit messages. 42/42 tests pass; fidelity gate green.

## Verdict

The methodology is now sound — the §3 tautology is genuinely gone and the
results reproduce exactly — but the headline numbers are thinner than the
commit-message framing suggests, and they rest on a single seed. The strongest
honest story is **"one structural mechanism explains both limits"**, which is a
better §3/§5 narrative than "g-computation wins."

## Verified results (seed 42)

| Metric | Severity 0.4 | Severity 1.0 |
|---|---|---|
| Naive MAE (overall) | 0.0873 | 0.0933 |
| G-comp MAE (overall) | 0.0832 | 0.0921 |
| Naive bias | -0.0201 | -0.0248 |
| G-comp bias | -0.0252 | -0.0271 |
| Strong-propagation: naive → gcomp | 0.0734 → 0.0598 (gap +0.0135) | 0.0800 → 0.0762 (gap +0.0038) |
| Overall gap (naive − gcomp) | +0.0041 | +0.0012 |

Selective-labels frontier (flat generator, `artifacts/clue_frontier.csv`): IPW
holds declined-cohort ECE through severity **0.4** (0.086), fails at 0.6
(0.154 vs target).

## What holds up

1. **The Gap-1 fix is real, not cosmetic.** `GComputationEstimator` is fit on
   approved rows only, uses only DAG *topology* (no SCM coefficients), and the
   per-unit no-op invariance handling (`counterfactual.py:499-502`) prevents
   mechanism-reconstruction noise from leaking into no-op queries. The oracle
   is honestly relabeled as a truth reference (~0 MAE by construction). The §3
   claim "a deployable method exists and is measurably less wrong where
   propagation matters" is now legitimate.

2. **The bank-feed gating trap is exercised.** `do(has_linked_bank_feed)` is a
   structural information switch in both the SCM and the estimator
   (`_effect_feed_switch`): flipping the gate reveals/hides the 6-node
   bank-feed block instead of overwriting one boolean column.

3. **Both limits share one cause — the best part of the result.** The IPW
   frontier breaks between severity 0.4 and 0.6, and the g-computation
   advantage collapses at full severity (+0.0135 → +0.0038), for the same
   structural reason: estimators fit on approved rows whose conditionals are
   distorted by selection on an *unobserved* confounder. Backdoor adjustment
   cannot fix unobserved confounding; IPW cannot fix broken positivity. One
   mechanism, two independently measured failure modes — a coherent §5.

## Sharpened critiques

1. **The win is smaller than the framing.** Overall MAE gap at severity 0.4 is
   +0.0041 (~5% relative). Even on the strong-propagation slice, gcomp's MAE
   of 0.0598 against a true effect size of ~0.116 means the deployable
   estimator still misses roughly **half the effect**. Naive misses ~75%. §3
   should say "directionally better, honestly far from recovery."

2. **G-comp's bias is slightly *worse* than naive** (-0.0252 vs -0.0201 at
   severity 0.4; -0.0271 vs -0.0248 at 1.0). MAE improves while systematic
   underestimation worsens slightly. Disclose preemptively.

3. **Single-seed results.** The strong-propagation gap is computed on 125
   queries from seed 42 alone; the +0.0038 full-severity gap is small enough
   to plausibly flip sign on another seed. → addressed by the seed sweep below.

4. **Two synthetic worlds.** The frontier runs on the flat `synthetic.py`
   generator while the counterfactual eval runs on the SCM. The cohort
   contract was designed so `SelectiveLabelsLoop` can consume SCM cohorts —
   unifying them would make Deliverable D read as one experiment.

## Recommendations (ranked by value-per-effort)

1. Multi-seed sweep of the counterfactual eval (in progress, results below).
2. Disclose the bias trade-off in the §3 writeup.
3. Point `SelectiveLabelsLoop` at the SCM for a unified world (nice-to-have).

## Seed sweep (multi-seed robustness)

Run 2026-06-10 across seeds {7, 13, 42, 101, 2026}, severities {0.4, 1.0},
900 queries each. Seed 42 reproduced the table above exactly (harness check).

### Severity 0.4 — the advantage is robust, and seed 42 understated it

| Seed | Strong-prop gap (naive − gcomp) | Overall gap |
|---|---|---|
| 7 | +0.0256 | +0.0042 |
| 13 | +0.0217 | +0.0060 |
| 42 | +0.0135 | +0.0041 |
| 101 | +0.0171 | +0.0009 |
| 2026 | +0.0177 | +0.0001 |
| **mean ± sd** | **+0.0191 ± 0.0046** | **+0.0031 ± 0.0025** |

- **No sign flips** on either metric: 5/5 seeds positive.
- Seed 42 (the one previously published) was the **most pessimistic** seed —
  the mean strong-propagation gap is ~40% larger than the single-seed number.
- Strong-propagation MAE across seeds: naive 0.0988 ± 0.0154 vs gcomp
  0.0797 ± 0.0135.
- The **bias trade-off is consistent**: gcomp's bias is more negative than
  naive's on **5/5 seeds** at this severity. It is a systematic property of
  the method here, not seed noise — disclose it as such.

### Severity 1.0 — the advantage is statistically zero; state it that way

| Seed | Strong-prop gap | Overall gap |
|---|---|---|
| 7 | +0.0011 | +0.0001 |
| 13 | **−0.0007** | **−0.0001** |
| 42 | +0.0038 | +0.0012 |
| 101 | +0.0014 | +0.0002 |
| 2026 | +0.0047 | +0.0007 |
| **mean ± sd** | **+0.0021 ± 0.0022** | **+0.0004 ± 0.0005** |

- The gap **flips sign on seed 13** and the mean is within one sd of zero.
  The anticipated failure mode is real: at full severity there is **no
  reliable g-computation advantage**, and §3/§5 must not claim a small one.

### What to write in Deliverable D

> At moderate selection (severity 0.4, inside the IPW frontier),
> g-computation reliably beats naive conditioning where interventions
> propagate: strong-propagation MAE gap **+0.019 ± 0.005 across 5 seeds, no
> sign flips**. At full severity the advantage is statistically
> indistinguishable from zero (+0.002 ± 0.002, sign flips on 1/5 seeds) —
> the same unobserved-confounder limit that breaks the IPW frontier between
> severity 0.4 and 0.6. G-computation also trades a small consistent
> increase in negative bias (5/5 seeds) for its MAE reduction.

This is a *cleaner* result than the single-seed version: the regime where the
method works is now sharply separated from the regime where nothing
deployable works, with the same structural cause for both.
