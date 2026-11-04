# Results — what the loop measured

Every figure here that is registered in the doc-number gate (`scripts/check_doc_numbers.py`)
recomputes from a CSV committed under `artifacts/` on every CI run; every artifact is pinned
by content hash in `artifacts/SHA256SUMS.json`. Limits are reported, not smoothed over.

## The result it produces

The loop escalates selection severity until correction fails and reports the **operating
frontier** — the last severity at which declined-cohort calibration still holds (target
ECE ≤ 0.10). From the committed runs (`artifacts/loop_frontier*.csv`, seed 42):

| Selection severity | 0.0 | 0.2 | 0.4 | 0.6 |
|---|---|---|---|---|
| Naive declined ECE (flat world) | 0.021 | 0.045 | 0.108 | 0.161 |
| **IPW-corrected** (flat world) | 0.020 | 0.038 | **0.086 ✓** | **0.154 ✗** |
| **IPW-corrected** (SCM world) | 0.036 | 0.038 | **0.097 ✓** | **0.244 ✗** |

On **this seed** both worlds land the frontier at severity 0.4, and the counterfactual
deliverable breaks at the same boundary: across 25 seeds, g-computation cuts
strong-propagation counterfactual MAE from 0.099 to 0.086 (−13.5%, positive on 24/25 seeds,
Wilcoxon p = 1.5e-7; on an independent spaced seed set: 22/25, p = 1.6e-6) *inside* the frontier — and collapses to a negligible +0.0017 at full
severity, where **no deployable advantage is claimed**. v1–v3 read one cause into both:
selection through an **unobserved confounder**, which backdoor adjustment and IPW cannot fix.
v4 then tested that attribution by direct intervention and **withdrew it** — the wall stands
with the confounder switched off (see
the cause, tested (the v4 section below)). The measured limit — not an
unverifiable score — is still the deliverable; its cause is now measured as open.

### The frontier is a distribution, not a point (v2)

A frontier quoted from one seed is a figure published without an error bar. `v0.2.0` runs the
loop across the full 25-seed set (`artifacts/frontier_sweep.csv`) — and **seed 42 turns out to
sit at the optimistic end**:

| World | min | median | max | seeds at 0.4 | seeds at 0.2 |
|---|---|---|---|---|---|
| flat | 0.2 | **0.4** | 0.4 | 15/25 | 10/25 |
| SCM | 0.2 | **0.2** | 0.4 | 11/25 | 14/25 |

In the SCM world, on this seed set, the *majority of seeds fail one step earlier than the
headline*: the median frontier is **0.2**, and seed 42's 0.4 is a minority outcome (11/25). The honest statement is
that the operating frontier is **0.2–0.4 depending on the draw**, not a clean 0.4 — the
single-seed table above is a valid instance of it, not its center. Nothing about the boundary
changes; what changes is how precisely it can be quoted. (The mechanism attribution itself
was later withdrawn by v4's interventional test — see below.)

*Caveat on the sweep:* loop seed `s` consumes generator seeds `s..s+7`, and the 25-seed set has
gaps smaller than 8, so some runs share feature draws. No two runs duplicate a cohort, but the
25 rows are not fully independent — the set is kept for comparability with the counterfactual
sweep that uses it.

*Caveat, measured (2026-07-29):* both sweeps were re-run on a spaced set — seeds
{1000 + 16i, i = 0..24}, spaced widely enough that no two runs **within the same generator**
(loop sweep) or **at the same severity** (counterfactual sweep) share any consumed seed; the
same seed across severities/generators stays deliberately paired
(`scripts/run_spaced_sweeps.py`; `artifacts/seed_sweep_spaced.csv`,
`artifacts/frontier_sweep_spaced.csv`). Two different verdicts:

- **Counterfactual — independent replication; the effect survives.** +0.0129 ± 0.0102,
  positive on 22/25 seeds, Wilcoxon p = 1.6e-6 (recompute:
  `python scripts/paired_significance.py --sweep-csv artifacts/seed_sweep_spaced.csv`); at
  full severity the spaced gap is +0.0024 ± 0.0030 — same conclusion, significant in sign and
  negligible in magnitude. A source audit during this rerun found a counterfactual run
  consumes only seeds `{s, s+1000}`, so the *original* counterfactual set was already
  cross-run independent within each severity: the seed-overlap caveat above genuinely applies
  to the loop sweep only, and the move from p = 1.5e-7 (24/25) to p = 1.6e-6 (22/25) is
  replicate variability between two valid designs, not a de-biasing.
- **Frontier — the overlap was real here, and removing it moves the center.** On the spaced
  set the distribution shifts toward 0.4: flat median 0.4 (18/25 at 0.4, 7/25 at 0.2), SCM
  median **0.4** (15/25 at 0.4, 10/25 at 0.2). The overlapping set's SCM median of 0.2 does
  **not** replicate on seed-disjoint runs; what survives is the range — 0.2–0.4 depending on
  the draw — with the independent draw putting the SCM center at 0.4.

Reproduce the headline from committed evidence: `python scripts/paired_significance.py`.
The full independent assessment (methodology, all numbers, what didn't hold) is the
accompanying article, [`docs/assessment.md`](https://github.com/hossainpazooki/closed-loop-default-detection/blob/master/docs/assessment.md) — a **dated snapshot**, written
against the single-seed frontier and not retro-fitted with the distribution above.

### The cause, tested by intervention (v4)

Every claim above measured the worlds at their **default** confounder strength. v4 makes that
strength an explicit axis: two additive knobs sweep `unobserved_strength` over
{0, 0.2, 0.4, 0.55, 0.7, 1.0} in both worlds — 300 loop runs and 450 counterfactual evals
(`artifacts/surface_frontier.csv`, `artifacts/surface_counterfactual.csv`) — against four
pre-registered confirmatory hypotheses (Holm-corrected, m = 4, sign test AND Wilcoxon plus
effect floors, the falsification statement written before the data; spec Rev 1.2). The
pre-registered attack fired: all four hypotheses were **not confirmed**, and the one-cause
reading is withdrawn as measured, not softened:

- **The wall stands with the confounder off.** At strength 0.0 the flat world's frontier sits
  at 0.4 on 25/25 seeds, and the SCM median is the same 0.4 — the frontier's *existence* is
  not confounder-caused.
- **The axis is real but only bites at the extreme:** median frontier severity is **0.4** at
  every strength up to 0.7 and moves to **0.2** only at strength 1.0, in both worlds. At the
  flat default a minority effect exists — 7/7 of the seeds that moved did so in the predicted
  direction (Holm-adjusted sign-test p = 0.031) — but it sits below the pre-registered
  one-step floor. The strength-1.0 move was observed post-hoc on these seeds. It has since
  been tested on fresh seeds under its own pre-registration (next section).
- **The counterfactual gap runs opposite the predicted direction:** the median
  strong-propagation gap at severity 0.4 goes +0.0152 → +0.0135 → +0.0090 as strength rises
  0.0 → 0.55 → 1.0.

What survives: every boundary measurement above — the frontier, its 0.2–0.4 range, the
counterfactual collapse. What is withdrawn: the sentence that one cause explains them.
Recompute everything: `python scripts/surface_stats.py` (fail-closed on missing cells;
enforces the byte-identity embed gate against the committed re-baseline).

### The strength-1.0 move, replicated on fresh seeds

*Verified experiment, not verified result.* The move at strength 1.0 was an observation, so
it was re-run as a test: 300 loop runs over the same six strengths, on 25 seeds no committed
artifact had consumed (`artifacts/strength_replication_frontier.csv`). It was **pre-registered
by digest**: the specification's SHA-256 was committed in
[`PREREGISTRATION.md`](https://github.com/hossainpazooki/closed-loop-default-detection/blob/master/PREREGISTRATION.md) before the first fresh seed ran. The
specification itself is held outside this repository, so the digest fixes the document
and its date and does not yet let a reader check its text. The hypotheses, floors and
reading rules it registers are stated in full in the analysis script's docstring.

The observation replicated in **2 of 2** worlds on 25 fresh seeds.

- **Primary outcome, calibration error.** From strength 0 to strength 1.0 the declined-pool
  calibration error at severity 0.4 rose by a median of +0.0515 in the flat world, on 25/25
  seeds (confirmed), and by +0.0201 in the SCM, on 20/25 seeds (confirmed). The SCM clears its
  floor of 0.0130 by 0.0070.
- **Secondary outcome, the frontier.** The frontier moves in grid steps, so a confirmed
  one-step move sits on its floor by construction; what differs is the margin. The flat
  frontier receded on 19 of 25 seeds and advanced on 0 (confirmed on its floor); the SCM
  frontier receded on 13 of 25 and advanced on 2, **confirmed on its floor** — 13 is exactly
  what the median needs, and one fewer would fail.
- **Where it starts.** On the fresh seeds the median frontier first moves at strength 1.0 in
  the flat world and at strength 0.7 in the SCM. The v4 sentence above describes the v4
  seeds; this one describes these.
- **The overlap flag, descriptively.** At strength 0 the flag fired at the failing severity
  on 24 of 25 flat runs and 17 of 25 SCM runs. The pre-stated reading rule does not withdraw
  the overlap explanation, and it cannot confirm it: the flag and the failure both follow
  severity, and within severity 0.4 the diagnostics do not separate failing runs from passing
  ones.

What this supports: the confounder does not build the wall, and at full strength it moves
it. What builds the wall at strength 0 is tested by intervention in the next section.
Recompute everything: `python scripts/strength_replication_stats.py` (fail-closed on missing
cells, on an unevaluable family, and on any run that consumed a spent seed).

### Losing overlap by hand: segmented selection at strength 0

*Verified experiment.* The two sections above leave the wall at strength 0 unexplained: the
confounder does not build it, and the leading candidate, an overlap wall, had only been seen
through a flag that rises with severity. This experiment removes overlap directly. A
segmented selection policy splits each cohort into five equal-mass segments by the rank of
one observed feature and funds segment 0 at `1 − depth` of the common rate, sharing the
freed volume among the other four, so the approval rate is unchanged, the features, planted
defaults and scores are byte-identical, and only the funding mask moves. Nothing is hidden:
every cell runs with the confounder switched off (`unobserved_strength = 0`). 400 loop runs
(`artifacts/segment_frontier.csv`): the global cutoff; depths {0, 0.5, 1} on
`aggregate_credit_utilization` (high end) and on `vintage_years` (low end), both worlds; and a
placebo knockout on `requested_amount`, which carries no risk, flat world only. It was
**pre-registered by digest** in [`PREREGISTRATION.md`](https://github.com/hossainpazooki/closed-loop-default-detection/blob/master/PREREGISTRATION.md); the matrix
started after that commit was public. The seeds are the v4 surface's strength-0 seeds, on
purpose: the legacy cell must reproduce the surface's rows byte for byte (gate I-C1).

- **Primary outcome, calibration error at severity 0.** Knocking the top utilization segment
  out entirely (depth 1 against depth 0), the control lever's declined-pool calibration error
  rose by a median of +0.0213 in the flat world, on 24/25 seeds (confirmed), and by +0.0268 in
  the SCM, on 24/25 seeds (confirmed), over re-cut floors of 0.0064 and 0.0085: the noise of
  re-cutting inside segments with no rate change, measured in the same experiment.
- **Secondary outcome, the frontier.** The flat frontier receded on 13 of 25 seeds and
  advanced on 0 (confirmed on its floor); the SCM frontier receded on 15 of 25 and advanced on
  0 (confirmed on its floor). As in the replication, a one-step move on a 0.2 grid sits on its
  floor by construction, and 13 is exactly what the flat median needs. The cell medians do not
  show it (both 0.4 in the flat world); the paired recession is carried by the seeds whose
  depth-0 frontier was 0.6 and by the seeds that fell to 0.2 or 0.
- **Placebo.** The same knockout on a feature with no risk coefficient came out at a median
  of +0.0008 on 14/25 seeds and **held**.
- **The falsification statement, applied.** Both frontier hypotheses are confirmed, so by the
  registered rule the overlap-wall explanation is **stated as measured**: removing overlap in
  an observable, with nothing hidden, reproduces the wall. Both confirmations sit on their
  floors with no margin.

**A correction made after the data were seen, disclosed.** The analysis script compared the
raw median to the 0.2 floor with `>=`. The flat median was one grid step stored as
0.6 − 0.4 = 0.19999999999999996, so the script first printed the flat frontier hypothesis as
not confirmed, and the explanation as not supported, while the SCM's exactly-stored 0.2
cleared. An independent recompute from the raw CSV found it. The comparison now tolerates
10⁻⁹ (`scripts/segment_stats.py` and `scripts/surface_stats.py`, three pinned regression
tests); the committed v4 statistics re-generate byte for byte under it, and the change can
only turn a false "not confirmed" into a confirmation, never the reverse. The registered
rule, one severity step, is unchanged.

What this supports: at strength 0 the wall is an overlap wall. What it does not: that overlap
is the whole story where the confounder is on, since at full strength the confounder moves
the wall too. The diagnostic flag fired on every round of every depth-1 cell, passing or
failing, so under a knockout it cannot discriminate (descriptive, by design). Recompute
everything: `python scripts/segment_stats.py` (fail-closed on missing cells and on I-C1).

## Pricing the frontier (v2)

Calibration says *whether* the model is wrong on the declines; it does not say **what being
wrong costs**. v2 adds an expected-maximum-profit (EMP) reporting axis — computed from the
same in-process scores the loop already measures, and **never** a loop-control input (ECE
still decides pass/fail and the frontier). Two variants run side by side:

| Variant | Parameters | What it answers |
|---|---|---|
| `empc` — literature EMPC | Verbraken et al. (2014) prior: `p0=0.55, p1=0.10, ROI=0.2644` | benchmark-comparable: what the standard measure says |
| `emp_h` — harness-derived | this harness's own economics + **planted** default timing | what the loan structure actually pays |

**The two disagree — and the disagreement is the finding.** In the SCM world they move in
opposite directions as selection severity rises (from `artifacts/loop_frontier_scm.csv`,
declined subpopulation, seed 42):

| Selection severity | 0.0 | 0.2 | 0.4 | 0.6 |
|---|---|---|---|---|
| Literature `empc` (naive) | 0.0217 | 0.0331 | 0.0416 | **0.0420 ↑** |
| Harness `emp_h` (naive) | 0.0387 | 0.0297 | 0.0139 | **0.0024 ↓** |

The convenience prior **misprices this loan structure**: it assumes `ROI = 0.2644` where a
60-day daily-ACH loan actually returns `0.0875` (3% origination fee + 5.75% term interest) —
a **3.0× overstatement** — and puts **55% of defaults at full recovery where the harness plants
1.2%** (prior mean λ = 0.275 vs harness 0.419). Priced honestly, the profit on the declined
pool collapses to near-zero at the frontier; priced by the literature prior, it appears to
*grow*. Same model, same scores, opposite conclusion.

**Reading caveats — the boundary of what this measures:**

- **Raw EMP moves with world hardness.** A riskier declined pool changes EMP even for a
  perfect model, so a cross-severity EMP delta is *not* pure model signal. Read the two
  variants against each other at fixed severity, not the trend in isolation.
- **`emp_h` rests on unfitted timing.** `days_to_default` is planted but independent of
  features and risk given default — spec-shaped, never validated against real recovery data.
  So `emp_h` is a **verified experiment, not a verified result**: the arithmetic is exact, the
  timing distribution is an assumption.
- **Post-term defaults are imputed.** ~22.5% of planted defaults land at day 90, past the
  60-day term, and the generator does not model their payment history; they are priced at the
  cohort's mean in-term loss fraction (a stated convention, not measured truth).
- **`emp_h` is SCM-only.** The flat generator plants no timing, so its `emp_h` columns are
  empty by design; only `empc` is reported there.

Exploration now carries a price tag too. From `artifacts/exploration_frontier.csv` (SCM,
seed 42, 10% budget, severity 0.6): the lever buys **157 labels for $439,578** — about
**$2,800 per label**, of which 56 are realized defaults. That is the cost of *identification*,
in dollars a lender can see, on the only lever that buys it rather than reweighting what is
already identified.

## Pricing the feedback loop (v3)

`v0.3.0` prices the **dynamic** regime, where the model's own approvals create its next
training set: three arms (treatment = retrain each generation; **frozen** = generation-0
model deployed forever; **prior** = prior-policy funding), 25 spaced seeds × 3 severities ×
2 exploration rates × 12 generations = **450 runs**
(`artifacts/feedback_profit_sweep.csv`), with three pre-registered hypotheses tested as
within-seed paired contrasts on realized funded-book P&L at severity 0.4, Holm-corrected.
Every number below recomputes via `python scripts/feedback_sweep_stats.py`. All of it
consumes **planted, risk-unlinked default timing** — a verified *experiment*, not a
verified *result*.

| Hypothesis (severity 0.4, gens 1–11) | Median paired deficit | Sign | Verdict |
|---|---|---|---|
| H1 feedback accumulation costs money (treatment − frozen, ε=0) | **−0.0028** | 24/25 | **confirmed** (p_holm 2.3e-06, clears the 0.0018 noise floor) |
| H2 the policy switch costs money (frozen − prior, ε=0) | +0.0119 | 0/25 | **not confirmed — measured opposite in direction** |
| H3 exploration buys profit back (treatment ε=.05 − ε=0) | −0.0024 | 0/25 | **not confirmed** |

The decomposition v3 exists for came back one-for-three: letting the loop close on its own
labels measurably costs the book (H1), but at these severities the *switch* to model-based
funding is profitable relative to the prior policy (H2's predicted sign was wrong — reported
as measured, not softened), and 5% exploration does not pay for itself in-window (H3; the
policy-book-only secondary H3a is negative too). The **H4 integrity control** — frozen-arm
paired difference must equal the explored slice's own P&L *exactly* — holds with max |error|
1.0e-10 across all 900 checked rows, and the answer to the v2-banked question is re-verified at 25 seeds:
the declined-ECE alarm fires at generation 1–2 in every ε=0 run (severity 0.4: 25/25 at
generation 1). Full mechanics in [`docs/how-it-works.md`](how-it-works.md); gates in
[`docs/validation.md`](validation.md).
