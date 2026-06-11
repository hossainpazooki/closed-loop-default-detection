# FABLE.md — Updated Methodology & Results Assessment

> Independent review of `closed-loop-default-detection` after PR #1
> (`feat/causal-gcomputation-and-gating`, merged 2026-06-06).
> All numbers below were **re-verified by re-running the code**, not copied from
> commit messages. 50/50 tests pass; fidelity gate 51/51 green.
>
> **UPDATE 2026-06-11 — bank-feed leak fixed (was deferred).** The
> `requested_amount_to_observed_revenue` leak (§"pre-existing issues" #2) was
> gated (design a) and the certification re-run on the corrected SCM. Headline
> shifts: severity-0.4 strong-prop gap **+0.0191 ± 0.0046 → +0.0133 ± 0.0068**
> (still 5/5 positive, ~19% → ~13% relative); severity-1.0 gap **+0.0021 → +0.0017
> ± 0.0013**, now uniformly positive (old seed-13 sign flip gone) but collapsed ~an
> order of magnitude. Operating frontier still 0.4. All tables below are the
> corrected post-fix numbers.

## Verdict

The methodology is now sound — the §3 tautology is genuinely gone and the
results reproduce exactly — but the headline numbers are thinner than the
commit-message framing suggests, and they rest on a single seed. The strongest
honest story is **"one structural mechanism explains both limits"**, which is a
better §3/§5 narrative than "g-computation wins."

## Verified results (seed 42)

| Metric | Severity 0.4 | Severity 1.0 |
|---|---|---|
| Naive MAE (overall) | 0.0872 | 0.0960 |
| G-comp MAE (overall) | 0.0842 | 0.0957 |
| Naive bias | -0.0219 | -0.0273 |
| G-comp bias | -0.0233 | -0.0308 |
| Strong-propagation: naive → gcomp | 0.0714 → 0.0635 (gap +0.0079) | 0.0802 → 0.0785 (gap +0.0017) |
| Overall gap (naive − gcomp) | +0.0029 | +0.0003 |

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
   advantage collapses at full severity (+0.0079 → +0.0017, seed 42), for the same
   structural reason: estimators fit on approved rows whose conditionals are
   distorted by selection on an *unobserved* confounder. Backdoor adjustment
   cannot fix unobserved confounding; IPW cannot fix broken positivity. One
   mechanism, two independently measured failure modes — a coherent §5.

## Sharpened critiques

1. **The win is smaller than the framing.** Overall MAE gap at severity 0.4 is
   +0.0029 (~3% relative, seed 42). Even on the strong-propagation slice, gcomp's
   MAE of 0.0635 against a true effect size of ~0.116 means the deployable
   estimator still misses roughly **half the effect**; naive misses ~60%. §3
   should say "directionally better, honestly far from recovery."

2. **G-comp's bias is slightly *worse* than naive** (-0.0233 vs -0.0219 at
   severity 0.4; -0.0308 vs -0.0273 at 1.0). MAE improves while systematic
   underestimation worsens slightly. Disclose preemptively.

3. **Single-seed results.** The strong-propagation gap is computed on 125
   queries from seed 42 alone; the +0.0017 full-severity gap is small enough
   that its sign and robustness needed the multi-seed check below.

4. **Two synthetic worlds.** The frontier runs on the flat `synthetic.py`
   generator while the counterfactual eval runs on the SCM. The cohort
   contract was designed so `SelectiveLabelsLoop` can consume SCM cohorts —
   unifying them would make Deliverable D read as one experiment.

## Recommendations (ranked by value-per-effort)

1. ~~Multi-seed sweep of the counterfactual eval~~ — **done**, results below.
2. Disclose the bias trade-off in the §3 writeup.
3. ~~Point `SelectiveLabelsLoop` at the SCM for a unified world~~ — **done**,
   results below (`feat/loop-on-scm`).

## Seed sweep (multi-seed robustness)

Run across seeds {7, 13, 42, 101, 2026}, severities {0.4, 1.0}, 900 queries
each. Seed 42 reproduces the verified table above exactly (harness check).

**Committed evidence:** the sweep is reproducible via
`scripts/run_seed_sweep.py` (one subprocess per eval), which writes
`artifacts/seed_sweep.csv` — both committed. The tables below are the corrected
post-leak-fix run (2026-06-11) on the gated SCM; the original pre-fix run is in
git history. The severity-1.0 mean gap (+0.0017 ± 0.0013) is uniformly positive
across seeds but collapsed ~an order of magnitude vs severity 0.4 — negligible,
no deployable advantage, as the bullets below state.

### Severity 0.4 — the advantage is robust across seeds

| Seed | Strong-prop gap (naive − gcomp) | Overall gap |
|---|---|---|
| 7 | +0.0133 | +0.0032 |
| 13 | +0.0169 | +0.0039 |
| 42 | +0.0079 | +0.0029 |
| 101 | +0.0225 | +0.0004 |
| 2026 | +0.0057 | -0.0009 |
| **mean ± sd** | **+0.0133 ± 0.0068** | **+0.0019 ± 0.0021** |

- **No sign flips on the strong-propagation slice**: 5/5 seeds positive. The
  overall (all-query) gap is thinner and goes marginally negative on one seed
  (2026, −0.0009) — the win lives where interventions propagate, not overall.
- Seed 42 (the one originally published) sits in the lower half of the five
  (2nd-smallest strong gap, +0.0079) — representative of the spread, not an
  outlier in either direction.
- Strong-propagation MAE across seeds: naive 0.0989 ± 0.0182 vs gcomp
  0.0856 ± 0.0138 (~13% relative reduction).
- The **bias trade-off is consistent**: gcomp's bias is more negative than
  naive's on **5/5 seeds** at this severity. It is a systematic property of
  the method here, not seed noise — disclose it as such.

### Severity 1.0 — the advantage collapses to negligible; state it that way

| Seed | Strong-prop gap | Overall gap |
|---|---|---|
| 7 | +0.0005 | −0.0003 |
| 13 | +0.0004 | +0.0001 |
| 42 | +0.0017 | +0.0003 |
| 101 | +0.0034 | +0.0005 |
| 2026 | +0.0023 | +0.0001 |
| **mean ± sd** | **+0.0017 ± 0.0013** | **+0.0001 ± 0.0003** |

- On the gated SCM the gap is **uniformly positive (5/5)** — the pre-fix seed-13
  sign flip is gone — but it has **collapsed by nearly an order of magnitude**
  vs severity 0.4 (+0.0017 vs +0.0133). It is marginally above zero, not
  statistically zero, but the effect size is negligible: at full severity there
  is **no deployable g-computation advantage**, and §3/§5 must not claim one.

### What to write in Deliverable D

> At moderate selection (severity 0.4, inside the IPW frontier),
> g-computation reliably beats naive conditioning where interventions
> propagate: strong-propagation MAE gap **+0.013 ± 0.007 across 5 seeds, no
> sign flips**. At full severity the advantage collapses by nearly an order of
> magnitude (+0.0017 ± 0.0013) — negligible and of no deployable value, the
> same unobserved-confounder limit that breaks the IPW frontier between
> severity 0.4 and 0.6. G-computation also trades a small consistent
> increase in negative bias (5/5 seeds) for its MAE reduction.

This is a *cleaner* result than the single-seed version: the regime where the
method works is now sharply separated from the regime where nothing
deployable works, with the same structural cause for both.

## Unified world: the loop now runs on the SCM (`feat/loop-on-scm`)

`SelectiveLabelsLoop` gained `generator="flat"|"scm"`; both the measure and
retrain cohorts route through one factory (same generator class, same
`TRAIN_SEED_OFFSET` no-leakage discipline). `run_clue.py --generator scm`
writes `artifacts/clue_frontier_scm.{csv,png}` without touching the flat
artifacts. Flat remains the default and is **byte-identical** to pre-change
behavior (frozen-baseline test with exact float equality).

### A blocker recon caught before implementation — worth a §5 footnote

The SCM's selection blend reused the exogenous draw behind the **observed**
`prior_underwriter_score` column (corr ≈ 0.92 with the selection score at
severity 0; an in-sample propensity model reached AUC ≈ 1.0). On the flat
generator, severity 0 means selection-at-random that *no* propensity model can
explain — so pointing the loop at the SCM naively would have silently inverted
the severity semantics and made the two frontiers incomparable. Fixed with a
gated `independent_selection_noise` flag (default off): a dedicated frozen
selection-noise node drawn *after* all existing draws, so the default RNG
stream — and therefore the fidelity gate — is untouched (sha256-verified
identical cohorts).

### Unified frontier result

| Severity | Naive declined ECE | IPW reweight | Passed |
|---|---|---|---|
| 0.0 | 0.0361 | 0.0359 | yes |
| 0.2 | 0.0398 | 0.0378 | yes |
| 0.4 | 0.1123 | 0.0969 | yes |
| 0.6 | 0.2728 | 0.2439 | **no** |

**The SCM frontier lands at severity 0.4 — the same operating frontier as the
flat world, now measured in the same synthetic world as the counterfactual
results.** Deliverable D can state one coherent claim: inside the frontier
(severity ≤ 0.4) IPW holds declined-cohort calibration *and* g-computation
reliably improves counterfactual MAE; beyond it, the unobserved confounder
defeats both, for the same structural reason.

Verification: 50/50 tests (8 new in `test_loop_scm.py`), fidelity gate 51/51
checks, adversarial diff review clean (determinism sha256-checked across
processes; IPW weights finite with NaN bank-feed columns).

### Pre-existing issues surfaced by the review (not from this change)

1. ~~`scipy` is used by `scm.py` but undeclared in `pyproject.toml`~~ — fixed
   (declared `scipy>=1.11`, 2026-06-10).
2. ~~`requested_amount_to_observed_revenue` is derived from ungated bank-feed
   revenue, leaking gated information for no-feed rows (`scm.py:666-673`).~~
   **FIXED 2026-06-11 (design a).** A single-seed diagnostic sized the leak at
   −42% of the seed-42 strong gap (+0.0135 → +0.0079), which made it
   load-bearing for the §3 magnitude rather than a cosmetic nuance, so it was
   gated to NaN for no-feed rows in both the SCM emit path and the estimator's
   feed-OFF switch; true risk (ungated `st.values`) is unchanged. Re-verified:
   fidelity 51/51 green (no check on the ratio), 50/50 tests green (one frozen
   strong-gap threshold moved 0.008 → 0.005 by design, FLAT byte-identity
   intact), 5-seed sweep + unified frontier re-run — corrected numbers are the
   tables above. The conclusion held (gap stays 5/5 positive at 0.4; frontier
   still 0.4); only the magnitudes shrank.
