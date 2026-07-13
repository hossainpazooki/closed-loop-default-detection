# FABLE.md — independent assessment of the causal deliverable (§3)

> **What this document is.** An independent review of `closed-loop-default-detection`'s
> counterfactual deliverable: does a *deployable* estimator recover the effect of
> `do(feature = value)` on probability-of-default (PD) better than naive conditioning,
> and where does it stop working? Every number here was recomputed by **re-running the
> code against the committed CSVs**, not copied from commit messages.
>
> **Read this top-to-bottom.** The bottom line is first; the final numbers are next;
> the dated change history and the superseded earlier run are in the appendices, out
> of the main flow.
>
> **Status:** 66/66 tests pass (pinned scikit-learn 1.9.0); fidelity gate 51/51 green.

---

## 1. Bottom line

The methodology is **sound**. The original §3 tautology — an "estimator" that secretly
called the ground-truth oracle, so it could not lose — is gone, replaced by a real
g-computation estimator fit only on observed data, and every result reproduces exactly.

But the win is **real and small**, not the decisive victory the early commit messages
implied. The strongest honest framing is *not* "g-computation wins." It is:

> **One structural mechanism explains both of the harness's limits.** Inside a
> moderate-selection frontier, g-computation reliably beats naive conditioning where
> interventions propagate. Past that frontier the advantage collapses — and the IPW
> calibration frontier breaks at the *same* severity, for the *same* reason: selection
> on an **unobserved confounder**. One cause, measured two independent ways.

That single coherent story is the result worth presenting in Deliverable D.

## 2. What is being assessed

The harness plants ground truth in a fidelity-checked structural causal model (SCM),
hides it through a realistic approval policy, and asks two questions that real lending
data structurally cannot answer:

- **Counterfactual accuracy (§3).** For `do(feature = v)`, how close is each estimator's
  post-intervention PD to the SCM's *true* interventional PD? Two estimators are graded:
  - **naive conditioning** — overwrite one column on a model fit to approved rows, then
    re-predict (ignores descendants, inherits selection bias);
  - **g-computation** — fit each child mechanism from observed data, clamp the target,
    and propagate the change through the fitted mechanisms.
  A third "oracle" path calls the SCM directly; it is labeled a **truth reference**
  (~0 MAE by construction), never scored as an estimator.
- **Calibration frontier (§4/§5).** As selection severity rises, how far can IPW
  reweighting hold calibrated PD on the **declined** (unlabeled) subpopulation before
  positivity breaks?

Throughout, **"strong-propagation"** means the slice of queries whose intervention
actually reaches descendants — the only slice where g-computation can differ from naive
conditioning, and therefore where the method is genuinely tested.

## 3. Headline result — 25 seeds, post-leak-fix

Counterfactual eval across **25 seeds**, 900 queries each, on the gated SCM. Evidence:
`artifacts/seed_sweep_25.csv` (+ `severity_curve.csv`, `paired_significance.csv`).

| Severity | Strong-prop MAE gap (naive − gcomp) | Positive seeds | Sign flips |
|---|---|---|---|
| **0.4** — inside the frontier | **+0.0134 ± 0.0085** (≈8 SE above zero) | **24 / 25** | seed 23 (−0.0041) |
| **1.0** — full selection | **+0.0017 ± 0.0020** | **20 / 25** | seeds 3, 11, 29, 71, 83 |

- **Where it works (severity 0.4).** Strong-propagation MAE is naive **0.0991 ± 0.0190**
  vs gcomp **0.0857 ± 0.0151** — a ~13.5% relative reduction. The overall (all-query) gap
  is thinner: +0.0019 ± 0.0017.
- **Paired significance** (formalizing "≈8 SE above zero"): at 0.4 the gap is significant
  with Wilcoxon signed-rank **p = 1.49e-7** and one-sample paired-t **p = 2.07e-8**. At
  1.0 the gap is significant *in sign* (Wilcoxon p = 1.44e-4) but its magnitude (+0.0017)
  is negligible — **statistical significance is not a deployable effect, and we claim
  none at full severity.**
- **The one trade-off to disclose.** G-computation buys lower MAE at the cost of slightly
  *worse* systematic underestimation: its bias is more negative than naive's on **25/25**
  seeds at 0.4 (mean −0.0295 vs −0.0244). State this preemptively, before a reviewer finds it.

**The advantage collapses along a measured severity curve** (original 5 seeds, paired
across all four severities):

| Severity | 0.4 | 0.6 | 0.8 | 1.0 |
|---|---|---|---|---|
| Strong-prop gap | +0.0133 ± 0.0068 | +0.0059 ± 0.0088 | +0.0050 ± 0.0029 | +0.0017 ± 0.0013 |
| Positive | 5/5 | 4/5 (seed 7 −0.0037) | 5/5 | 5/5 |

The shape is **sharp drop → plateau → floor**, not a smooth decline: ~63% of the total
collapse happens across the **0.4 → 0.6** step — the *same* boundary where the IPW frontier
breaks (§4) — then 0.6/0.8 is flat within noise, then a floor at 1.0. The 0.6/0.8 plateau
sits ~3× the 1.0 floor: degraded, not yet gone.

### Seed-42 reference point (for cross-checking a fresh run)

Seed 42 is the single seed the harness publishes in full. It sits in the *lower* half of
the 25-seed spread (2nd-smallest strong gap), so it is representative, not cherry-picked.

| Metric | Severity 0.4 | Severity 1.0 |
|---|---|---|
| Naive MAE (overall) | 0.0872 | 0.0960 |
| G-comp MAE (overall) | 0.0842 | 0.0957 |
| Naive bias | −0.0219 | −0.0273 |
| G-comp bias | −0.0233 | −0.0308 |
| Strong-prop: naive → gcomp | 0.0714 → 0.0635 (gap +0.0079) | 0.0802 → 0.0785 (gap +0.0017) |
| Overall gap (naive − gcomp) | +0.0029 | +0.0003 |

## 4. The unified world — both failure modes, one cause

The counterfactual eval and the calibration frontier now run in the **same** SCM world
(`SelectiveLabelsLoop` gained `generator="flat"|"scm"`; `run_clue.py --generator scm`).
The flat generator stays the default and is **byte-identical** to pre-change behavior
(frozen-baseline test, exact float equality).

**IPW calibration frontier on the SCM** (declined-cohort ECE, target 0.10):

| Severity | Naive declined ECE | IPW reweight | Passes |
|---|---|---|---|
| 0.0 | 0.0361 | 0.0359 | yes |
| 0.2 | 0.0398 | 0.0378 | yes |
| 0.4 | 0.1123 | 0.0969 | yes |
| 0.6 | 0.2728 | 0.2439 | **no** |

The SCM frontier lands at **severity 0.4 — the same operating frontier as the flat world**
(which agrees: IPW holds declined ECE to 0.086 at 0.4 and fails at 0.6 with 0.154,
`artifacts/clue_frontier.csv`). Now both deliverables live in one world, so Deliverable D
states a single claim:

> Inside the frontier (severity ≤ 0.4), IPW holds declined-cohort calibration **and**
> g-computation reliably improves counterfactual MAE. Beyond it, the unobserved confounder
> defeats both — backdoor adjustment cannot fix unobserved confounding, IPW cannot fix
> broken positivity. Same cause, two independently measured failure modes.

Verification: 66/66 tests (8 new in `test_loop_scm.py`), fidelity 51/51, determinism
sha256-checked across processes, IPW weights finite with NaN bank-feed columns.

## 5. What holds up

1. **The Gap-1 fix is real, not cosmetic.** `GComputationEstimator` is fit on approved
   rows only, uses only DAG *topology* (no SCM coefficients), and a per-unit no-op
   invariance guard (`counterfactual.py:499-502`) keeps mechanism-reconstruction noise out
   of no-op queries. The §3 claim "a deployable method is measurably less wrong where
   propagation matters" is now legitimate.
2. **The bank-feed gating trap is exercised.** `do(has_linked_bank_feed)` is a structural
   information switch in both the SCM and the estimator (`_effect_feed_switch`): flipping
   the gate reveals/hides the 6-node bank-feed block, instead of overwriting one boolean.
3. **The two-limits-one-cause story (§4) is the best part of the result.**

## 6. What to be careful about

1. **The win is small — say so.** Overall MAE gap at 0.4 is +0.0029 (~3%, seed 42). Even
   on the strong-propagation slice, gcomp's MAE of 0.0635 against a true effect size ~0.116
   still misses roughly **half** the effect (naive misses ~60%). Frame §3 as "directionally
   better, honestly far from recovery."
2. **The bias trade-off (§3) cuts against the method** — disclose it, don't wait to be asked.
3. **At full severity there is no deployable advantage** — the 1.0 column is negligible
   despite being sign-significant. Claim nothing there.

## 7. For Deliverable D (paste-ready)

> At moderate selection (severity 0.4, inside the IPW frontier), g-computation reliably
> beats naive conditioning where interventions propagate: strong-propagation MAE gap
> **+0.0134 ± 0.0085 across 25 seeds, positive on 24/25** (≈8 SE above zero, Wilcoxon
> p = 1.49e-7; the one flip is reported). The advantage collapses along a measured severity
> curve — +0.0133 → +0.0059 → +0.0050 → +0.0017 — with most of the collapse across the same
> 0.4 → 0.6 boundary where the IPW frontier breaks; at full severity it is +0.0017 ± 0.0020
> with sign flips on 5/25 seeds — significant in sign but negligible in magnitude, so we
> claim no deployable advantage there. G-computation also trades a small consistent increase
> in negative bias (25/25 seeds) for its MAE reduction. Evidence: `artifacts/seed_sweep_25.csv`,
> `artifacts/paired_significance.csv`.

## 8. Reproducing the numbers

```bash
pip install -e ".[dev]"                       # pins scikit-learn 1.9.0 / numpy 2.4.6
pytest                                         # 66/66
python scripts/run_seed_sweep.py               # -> artifacts/seed_sweep.csv (5-seed)
python scripts/paired_significance.py          # -> artifacts/paired_significance.csv
python scripts/run_clue.py --generator scm     # -> artifacts/clue_frontier_scm.{csv,png}
```

**Environment matters for exact reproduction.** HistGradientBoosting's float output shifts
across scikit-learn releases, so the committed numbers and the frozen byte-identity baseline
are pinned to **scikit-learn 1.9.0 / numpy 2.4.6** (Python 3.14.2). A clone on a different
sklearn will see the last decimals move and 3 environment-sensitive tests differ; the pin in
`pyproject.toml` / `requirements-dev.txt` makes "tests green / numbers reproduce" deterministic.

---

## Appendix A — change history

**2026-06-13 — Opus 4.8 audit & hardening pass** (`claude-opus-4-8[1m]`). An independent
audit recomputed every headline number from the committed CSVs (all reproduced to full
precision) and re-ran the suite **66/66** under the pinned environment. Eight changes:
(1) pinned scikit-learn 1.9.0 / numpy 2.4.6 + added `requirements-dev.txt`, so "tests green /
numbers reproduce" is no longer environment-dependent (a fresh clone on scikit-learn 1.8.0
previously failed 3 env-sensitive tests); (2) the sibling hackathon `causal.py` counterfactual
fallbacks now warn instead of silently returning the population mean; (3) added the paired
significance test (`scripts/paired_significance.py` → `artifacts/paired_significance.csv`);
(4) the README diagnostics note now flags small-n in-sample-AUC inflation; (5) reconciled the
test-count drift across docs to the canonical 66/66; (6) promoted the 25-seed run into the body
and demoted the 5-seed tables to Appendix B; (7) renumbered a duplicate METHODOLOGY section in
the sibling repo; (8) refreshed stale test-count snapshots in `SESSION_HANDOFF.md`. This rewrite
(top-to-bottom readability, changelog moved to appendices) is part of the same pass.

**2026-06-11 — bank-feed leak fix.** `requested_amount_to_observed_revenue` was derived from
*ungated* bank-feed revenue, leaking gated information to no-feed rows (`scm.py:666-673`). A
single-seed diagnostic sized the leak at −42% of the seed-42 strong gap (+0.0135 → +0.0079) —
load-bearing, not cosmetic — so it was gated to NaN for no-feed rows in both the SCM emit path
and the estimator's feed-OFF switch (true risk, ungated `st.values`, unchanged). Re-verified:
fidelity 51/51 green, 66/66 tests (one frozen strong-gap threshold moved 0.008 → 0.005 by design;
FLAT byte-identity intact). The conclusion held — gap stays 5/5 positive at 0.4, frontier still
0.4 — only the magnitudes shrank. **All tables in this doc are the corrected post-fix numbers.**

**2026-06-11 (later) — 25-seed extension.** The original 5-seed certification was scaled to 25
seeds (the original 5 plus 3,5,11,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83) at
severities {0.4, 1.0}, with the severity grid filled at {0.6, 0.8} on the original 5. Evidence:
`artifacts/seed_sweep_25.csv` (50 rows; the 10 original-seed rows are the untouched
`seed_sweep.csv` values), `artifacts/severity_curve.csv` (10 rows), driver
`artifacts/run_sweep_25_driver.py`. Skeptic-verified: stats recomputed from raw rows to full
precision; the seed-23 flip reproduces in a fresh subprocess (deterministic, not noise). The
mean held (+0.0133 → +0.0134) but the 5-seed interval **understated variance** (sd 0.0068 →
0.0085), and the original "no sign flips" / "uniformly positive" phrasing did **not** survive
scale (one flip at 0.4, five at 1.0). The 25-seed run is authoritative; the 5-seed tables are
in Appendix B.

**Origin & earlier fixes.** This document began as the independent review of PR #1
(`feat/causal-gcomputation-and-gating`, merged 2026-06-06), which closed the two original §3
gaps: the oracle-as-estimator tautology, and the bank-feed trap not propagating. `scipy` was
declared in `pyproject.toml` on 2026-06-10. The post-hackathon "close-the-loop" expansion
(feedback / exploration / diagnostics, see the README) was built from the lessons recorded here.

**A blocker caught before implementation (worth a §5 footnote).** Pointing the loop at the SCM
naively would have silently *inverted* the severity semantics. The SCM's selection blend reused
the exogenous draw behind the **observed** `prior_underwriter_score` column (corr ≈ 0.92 with the
selection score at severity 0; an in-sample propensity model hit AUC ≈ 1.0 — i.e. "severity 0"
was *not* selection-at-random, which is what it must mean). Caught in recon before implementation
and fixed with a gated `independent_selection_noise` flag (default off): a dedicated frozen
selection-noise node drawn *after* all existing draws, so the default RNG stream — and therefore
the fidelity gate — is sha256-identical.

## Appendix B — original 5-seed certification (superseded)

> Retained for the audit trail. The **25-seed numbers in §3 are authoritative**; the
> "no sign flips" / "uniformly positive" phrasings here did *not* survive scale (one flip at
> 0.4, five at 1.0 — see §3). Numbers are unchanged from the original run, preserved verbatim.
> Run across seeds {7, 13, 42, 101, 2026}, severities {0.4, 1.0}, 900 queries each; reproducible
> via `scripts/run_seed_sweep.py` → `artifacts/seed_sweep.csv`.

### Severity 0.4 — the advantage is robust across seeds

| Seed | Strong-prop gap (naive − gcomp) | Overall gap |
|---|---|---|
| 7 | +0.0133 | +0.0032 |
| 13 | +0.0169 | +0.0039 |
| 42 | +0.0079 | +0.0029 |
| 101 | +0.0225 | +0.0004 |
| 2026 | +0.0057 | -0.0009 |
| **mean ± sd** | **+0.0133 ± 0.0068** | **+0.0019 ± 0.0021** |

- No sign flips on the strong-propagation slice among these 5 seeds — but at 25 seeds one flips
  (seed 23, −0.0041; **24/25 positive**, see §3). The overall gap is thinner and goes marginally
  negative on one seed (2026, −0.0009): the win lives where interventions propagate, not overall.
- Seed 42 (originally published) sits in the lower half of the five (2nd-smallest strong gap,
  +0.0079) — representative of the spread, not an outlier.
- Strong-propagation MAE across these 5 seeds: naive 0.0989 ± 0.0182 vs gcomp 0.0856 ± 0.0138
  (~13% relative reduction).
- The bias trade-off is consistent: gcomp more negative than naive on **5/5** seeds here, and
  **25/25** at 25 seeds (naive −0.0244 vs gcomp −0.0295) — a systematic property, not seed noise.

### Severity 1.0 — the advantage collapses to negligible

| Seed | Strong-prop gap | Overall gap |
|---|---|---|
| 7 | +0.0005 | −0.0003 |
| 13 | +0.0004 | +0.0001 |
| 42 | +0.0017 | +0.0003 |
| 101 | +0.0034 | +0.0005 |
| 2026 | +0.0023 | +0.0001 |
| **mean ± sd** | **+0.0017 ± 0.0013** | **+0.0001 ± 0.0003** |

- On these 5 seeds the gap is uniformly positive — but at **25 seeds five flip** (seeds
  3/11/29/71/83; **20/25 positive**, +0.0017 ± 0.0020). It has collapsed by nearly an order of
  magnitude vs severity 0.4 (+0.0017 vs +0.0134) and is negligible with sign flips: at full
  severity there is **no deployable g-computation advantage**, and §3/§5 must not claim one.
