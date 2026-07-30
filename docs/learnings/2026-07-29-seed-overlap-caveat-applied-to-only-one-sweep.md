# The seed-overlap caveat applied to only one of the two sweeps

*2026-07-29. Status: verified (adversarial source audit during the spaced-seed
rerun, assessment III.2-1).*

## What was believed

Assessment Part III critique 1 (and the plan built on it) treated both 25-seed
sweeps as contaminated by cross-run seed sharing: "each run consumes seeds
`s..s+7`", the old set has gaps < 8, therefore the counterfactual p = 1.5e-7
and the frontier distribution both rest on non-independent replicates.

## What is true

The consumption pattern differs per pipeline, and the critique's premise held
for only one of them:

- **Loop/frontier runs** consume measure seeds `s..s+(rounds-1)` plus train
  seeds `s+TRAIN_SEED_OFFSET..` — the old set really does collide (10 run
  pairs per generator share at least one consumed seed, confirmed from the
  actually-consumed iterations in `frontier_sweep.csv`).
- **Counterfactual runs** (`run_counterfactual_eval`) consume only
  `{s, s+1000}` (generator/query stream `s`, model train seed `s+1000`;
  `counterfactual.py`, `config.TRAIN_SEED_OFFSET`). No pair of old seeds
  collides — the published counterfactual p-values were already cross-run
  independent within each severity.

So the spaced rerun *repaired* the frontier distribution (SCM median moved
0.2 → 0.4 once runs were seed-disjoint) but merely *replicated* the
counterfactual result (p = 1.5e-7 → 1.6e-6 is variability between two valid
designs, not de-biasing) — and the README now says exactly that, rather than
claiming the old p was anti-conservative.

## The lesson

A critique's premise needs the same refutation pass as a claim. "Consumes
`s..s+7`" was quoted from the loop's docstring and over-generalized to a
different pipeline with a different RNG budget; the error survived into a
published dated review (Part III stays frozen with it) and was only caught
because the skeptic pass on the rerun attacked the independence premise from
source instead of trusting the plan's framing. Before asserting that a seed
set is (or is not) contaminated, enumerate the consumed streams per pipeline
from the code — the answer is not a property of the seed set alone.
