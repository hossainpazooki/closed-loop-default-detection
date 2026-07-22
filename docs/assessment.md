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

> **2026-07-14:** a second dated assessment — **Part II: the v2 EMP layer (0.2.0),
> pre-publication** — is appended after Appendix B. The body above is the v1 snapshot,
> unmodified; Part II qualifies (does not retro-fit) two of its statements — see Part II §6.

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

---

# Part II — independent assessment of the v2 EMP layer (0.2.0, pre-publication)

*2026-07-14, Fable 5 (`claude-fable-5`). Assessed at the tree that will become `v0.2.0` —
built and gate-verified, **not yet published** (PyPI still serves 0.1.0; `CITATION.cff`
still reads 0.1.0 and flips at release). Every number below was recomputed from the
committed artifacts in this tree at the moment of writing, not quoted from build logs.
Spec under assessment: `docs/superpowers/specs/2026-07-13-cldd-v2-emp-design.md` (Rev 3).*

> **Status at assessment:** 149/149 tests pass (pinned scikit-learn 1.9.0 / numpy 2.4.6;
> junitxml: 0 failures, 0 errors, 0 skipped), `sphinx -W` clean, all 18 v1 columns of the
> committed frontier CSVs byte-identical after regeneration (EMP columns strictly appended).
> The fidelity gate was **not** re-run (private data; not runnable here) — and does not
> need to be: v2 touches no generator code, and the frozen flat baseline plus the v1-column
> byte-identity check bound the blast radius at zero.

## II.1 Bottom line

The v2 layer does what it claims and nothing it doesn't: EMP is **reporting only** — the
loop provably makes the same decisions it made in v1 — and the arithmetic of both variants
survived independent recomputation to zero delta. But the assessment's real product is two
results that **narrow what this repo may claim**, one of them about its own v1 headline:

1. **The operating frontier is a distribution, and the published 0.4 sits at its optimistic
   end.** Across the 25-seed sweep the SCM-world median frontier is **0.2**; seed 42's 0.4
   is a minority outcome (11/25). The flat world holds at median 0.4 (15/25).
2. **The literature EMPC prior misprices this loan structure**, exactly as the spec's
   decision record anticipated: priced by the standard prior, declined-pool profit *rises*
   with severity; priced by the harness's own economics, it collapses toward zero. Same
   scores, opposite conclusion — the disagreement is the deliverable.

Neither finding weakens the mechanism story (the unobserved confounder still explains the
failure); both tighten the honest phrasing of it.

## II.2 What was verified, and how

The build ran as a four-agent fan-out with an integration gate; its four adversarial
verifiers all died on a model-usage limit, so **every load-bearing claim below was instead
verified by the assessing model directly** — a substitution worth naming, since it trades
verifier independence for verifier capability. Methods and outcomes:

| Claim | Method | Outcome |
|---|---|---|
| `empc_literature` implements Verbraken et al. (2014) Eqs. 13/15 | independent re-derivation from the paper text; hand-enumerated convex hulls on 3 cases; direction probe | match to **0.00e+00**; `optimal_fraction` confirmed as the *approved* share |
| harness economics (λ, profits, day-90 imputation, empty-body fallback) | hand arithmetic from `TERM_DAYS`/`APR`/`ORIGINATION_FEE_RATE`; brute-force cutoff scan; monotone-transform probe | exact on every case; `emp_harness` invariant under monotone maps; flat cohorts return `None` |
| the new tests would catch a broken implementation | **mutation testing**: 5 injected bugs (hull skipped, score magnitudes used, ranking reversed, p1 term dropped, λ-cap removed) | **5/5 caught** (3–5 failures each); tests are non-vacuous |
| v1 numbers untouched by the wiring | per-cell string comparison of regenerated CSVs vs `git show HEAD:` | all 18 v1 columns byte-identical, both worlds; 11 EMP columns appended |
| `exploration_cost` equals the spec's economics | independent recomputation from raw planted columns on a live SCM cohort | match to **0.00e+00** (157 explored, 56 defaults, $439,577.96) |

Known untested edge path, disclosed by its own builder and still untested at assessment:
the `k == m` hull-terminal fallback in `empc_literature` (reachable only for unusual
pi0/ROI combinations; the shipped prior never reaches it). It is flagged in the source.

## II.3 Finding 1 — the frontier is a distribution (`artifacts/frontier_sweep.csv`)

First loop-level seed sweep (25 seeds x both worlds, `scripts/run_frontier_sweep.py`):

| World | frontier histogram | median | seed 42 |
|---|---|---|---|
| flat | 0.2 × 10, 0.4 × 15 | **0.4** | 0.4 |
| SCM | 0.2 × 14, 0.4 × 11 | **0.2** | 0.4 |

The honest claim is an operating frontier of **0.2–0.4 depending on the draw**, with the
flat world centered at 0.4 and the SCM world at 0.2. A single-seed frontier was the same
shape of defect as a figure published without an error bar; v2 removes it. Caveat carried
with the artifact: loop seed *s* consumes generator seeds *s..s+7* and the 25-seed set has
gaps < 8, so runs share feature draws — rows are correlated, not independent.

## II.4 Finding 2 — the convenience prior misprices this loan (`artifacts/loop_frontier_scm.csv`)

Declined subpopulation, naive lever, seed 42, severity 0.0 → 0.6:

| Variant | 0.0 | 0.2 | 0.4 | 0.6 | trend |
|---|---|---|---|---|---|
| `empc` (literature prior) | 0.0217 | 0.0331 | 0.0416 | 0.0420 | **rising** |
| `emp_h` (harness economics) | 0.0387 | 0.0297 | 0.0139 | 0.0024 | **collapsing** |

Root cause, measured: the prior assumes ROI = 0.2644 where this 60-day daily-ACH structure
returns 0.0875 (fee 3% + 5.75% term interest) — **3.0× the actual return** — and places 55%
of defaults at full recovery where the harness plants ~1.2% (prior mean λ 0.275 vs planted
0.419). A lender reading only the benchmark-standard number would conclude the declined pool
grows more profitable as selection hardens; priced honestly it is nearly worthless at the
frontier. Exploration is priced on the same economics: at severity 0.6 a 10% budget buys
157 labels for $439,578 (~$2,800/label, 56 realized defaults) —
`artifacts/exploration_frontier.csv`.

## II.5 What did not survive this assessment (errors caught, by whom)

1. **A spec claim, retracted.** Rev 2 asserted harness EMP is "mathematically EMPC with an
   empirical h(λ)". False: they are different functionals (EMPC integrates LGD uncertainty
   *inside* an expectation of the maximum; `emp_h` maximizes realized profit — Jensen
   separates them even at identical h(λ)), on top of different ROI and h(λ). Corrected in
   the spec (Rev 3) before any doc repeated it.
2. **A wrong README number, caught by this repo's own rule.** The first draft cited 163
   labels / $458,467 for exploration at severity 0.6 — from an ad-hoc script that priced
   round 0's RNG draw instead of round 3's. The committed artifact says 157 / $439,578.
   "Numbers come from committed artifacts" exists precisely for this failure.
3. **A vacuous verification, caught before it certified anything.** The first mutation
   harness reported all mutants "caught" — because they crashed on an import error before
   running a single test. Fixed; only then did the 5/5 result above become evidence.
4. **The adversarial-verifier fan-out itself failed** (usage limits), degrading the planned
   independent-skeptic pass into the self-verification documented in §II.2.

## II.6 What Part I statements this qualifies

- Part I §4: *"The SCM frontier lands at severity 0.4 — the same operating frontier as the
  flat world."* True **for seed 42**, the only seed the harness published in full at the
  time. As a distribution the SCM frontier centers at **0.2** (14/25 seeds); the flat world
  keeps its 0.4 median. The two-limits-one-cause mechanism is unaffected.
- Part I §3's *"seed 42 … is representative, not cherry-picked"* referred to the
  **counterfactual gap**, where it remains true (2nd-smallest strong gap of 25). For the
  **frontier** metric, seed 42 sits at the optimistic end. The two metrics must not be
  blurred: one seed can be representative on one axis and favorable on another.
- Part I's tests/fidelity status line (66/66, 51/51) is its dated snapshot; the current
  tree is 149/149 with the fidelity gate unaffected by v2 (no generator code touched).

## II.7 What must stay caveated after publication

- **`emp_h` rests on planted, unfitted timing** — `days_to_default` is independent of
  features and risk given default, spec-shaped but never validated against real recoveries.
  Verified experiment, not verified result.
- **~22.5% of planted defaults (day-90 mass) are priced by a stated imputation** (cohort
  mean body λ), not measured truth.
- **Raw EMP moves with world hardness** — cross-severity EMP deltas conflate world
  difficulty with model failure; read the variants against each other at fixed severity.
- **EMP is not a gate** — any future proposal to route loop control through EMP is a
  design change against the spec's decision record, not a tuning knob.

## II.8 Reproducing this assessment's numbers

```bash
pip install -r requirements-dev.txt && pip install -e ".[dev]"   # pins: sklearn 1.9.0 / numpy 2.4.6
pytest                                          # 149 passed
python scripts/run_loop.py --generator scm      # -> artifacts/loop_frontier_scm.{csv,png} (EMP columns)
python scripts/run_frontier_sweep.py            # -> artifacts/frontier_sweep.csv (25 seeds x both worlds)
python scripts/run_exploration_sweep.py         # -> artifacts/exploration_frontier.csv (exploration_cost)
```

*End of Part II. This section is a dated snapshot of the pre-publication tree; if 0.2.0
ships with changes beyond version metadata, a new dated entry supersedes it rather than
editing it.*

---

# Part III — post-publication methodological review (0.3.0, released)

*2026-07-22, Fable 5 (`claude-fable-5`). Written at `416e3a2`, after the `v0.3.0` release
(live on PyPI, effect-verified from a clean consumer venv) and alongside the accompanying
essay's publication. Parts I and II are untouched, per this document's own rule. This part
records two things: the pre-publication verification pass (what was recomputed and held),
and the methodological review it produced — a ranked list of critiques and **proposed**
tests. The proposed tests are exactly that: none has been run. The
implemented-vs-proposed boundary is tagged line by line.*

> **Status at review:** every empirical figure in the essay recomputed from the committed
> artifacts at the `v0.3.0` tree and matched (III.1); marginal-fidelity gate **re-run
> 2026-07-22 against the private dataset: PASSED, 51/51 rows green** (36 counted toward
> the verdict + 15 informational), exit 0 — the first reconfirmation since the carried-over
> claim flagged in the 2026-06-26 handoff; suite 203 under pins; CI 15/15.

## III.1 The verification pass [verified]

Recomputed from artifacts, not quoted from docs — all exact: seed-42 severity-0.4 MAE
0.087160 → 0.084219 (overall gap +0.0029, strong-propagation +0.0079;
`seed_sweep_25.csv`); severity-1.0 overall gap +0.0003, strong-propagation +0.0017;
declined-ECE 0.0969/0.1123 at severity 0.4 and 0.2439/0.2728 at 0.6
(`loop_frontier_scm.csv`); frontier distribution SCM median 0.2 (14/25 at 0.2, 11/25 at
0.4), flat median 0.4 (`frontier_sweep.csv`). Math spot-checks: the 24/25 sign-test p is
exactly 26/2²⁵ = 7.749e-07; −13.5% = 0.0134/0.099; `paired_significance.py` reproduces
W = 322, p = 1.490e-07 (severity 0.4) and the severity-1.0 significant-in-sign /
negligible-in-magnitude refusal. One essay ambiguity was fixed pre-publication: the
maximal-severity "+0.0003" is the *overall* gap (strong-propagation is +0.0017).

## III.2 Methodology critiques, ranked (each with its proposed test)

1. **[proposed] Pseudo-replicated seeds under the headline p-values.** The 25-seed set
   behind `seed_sweep_25.csv`/`frontier_sweep.csv` has inter-seed gaps < 8 while each run
   consumes seeds `s..s+7` (disclosed in the README caveat), so the "paired replicates"
   share feature draws and Wilcoxon/paired-t independence is violated — p = 1.5e-07 is
   anti-conservative. The v3 spec rejected this exact seed set for this exact reason and
   built the spaced set {1000+16i}; the v1/v2 headline claims still rest on the
   overlapping one. The 24/25 sign is robust; the quoted significance is not what an
   independent design would give. *Test:* re-run the counterfactual and frontier sweeps on
   the spaced set; quote those p-values. The cheapest high-value robustness run available.
2. **[proposed] "Both walls are the same wall" is a coincidence of location, not yet a
   demonstrated mechanism.** With four severities {0, 0.2, 0.4, 0.6}, two independent
   failure modes landing on the same grid step is not rare. The harness owns the world, so
   the mechanism claim is testable interventionally: *reveal the confounder* — append `u`
   to the estimators' feature set (equivalently run at `unobserved_strength = 0`) and show
   both walls move together or vanish; negative control: append an irrelevant noise column
   and show neither moves. If both walls disappear when `u` is observed, "one cause,
   measured two ways" becomes an ablation result. The strength-0 point lies on the planned
   v4 Option A surface, so this is v4's natural opening move, not extra work.
3. **[proposed] The IPW wall's location may partly encode a hard-coded constant.**
   `selection_adjusted_weights` clips propensity to (0.05, 0.95) — a silent max weight of
   20 (`model_pd.py:170,192`). At severity 0.6 the failure could be (a) unobserved
   confounding, as claimed, (b) clipping bias — the correction needs weights the clip
   forbids, or (c) weight variance; only (a) supports the published story, and (b) sits
   exactly on the disclosed boundary between confounder-positivity and cutoff-positivity
   failure. *Test:* frontier sensitivity to clip ∈ {(0.01, 0.99), (0.05, 0.95), none} plus
   a Hajek-normalized variant. Wall doesn't move → the confounding claim is clean; moves →
   the README owes one sentence.
4. **[proposed] G-computation is graded holding the true graph.** Disclosed (topology,
   never coefficients), but a real lender lacks the true topology too, so "deployable"
   mildly overreaches. *Test:* graph-misspecification sensitivity — remove one true edge,
   add one spurious edge, re-grade. The +0.0079 gap surviving a mildly wrong graph earns
   "deployable"; a sign flip is a publishable finding in itself.
5. **[proposed] The strong-propagation subset is truth-defined.** Legitimate in a graded
   world, but no practitioner can identify "queries whose effects propagate" without the
   SCM. *Test:* none needed — one disclosure sentence in the docs, if not already present,
   that the subset is defined from the answer key, not from anything observable.
6. **[proposed] No within-seed uncertainty on ECE cells.** v2 fixed the across-seed spread
   (the frontier distribution); within a cell, 10-equal-width-bin ECE on a finite cohort is
   itself noisy and 0.0969 clears the 0.10 target by ~3%. *Test:* bootstrap CI on
   declined-cohort ECE at severity 0.4, reported as sensitivity only — the 0.10 constant
   and the binning remain registered defects per the v3 spec §9, not knobs.

## III.3 Engineering tests proposed

- **[proposed] Mechanize the doc-number gate.** The "numbers come from committed
  artifacts" rule has fired twice, manually (II.5), and the essay adds a third quoting
  surface. A `check_doc_numbers` script diffing quoted figures against artifact recomputes,
  wired into CI, turns the repo's best manual discipline into a gate. Highest engineering
  ROI on this list.
- **[proposed] Systematic mutation run** (`mutmut` or equivalent) over `src/cldd/` with a
  survival report — mutation testing here has been ad hoc (five planted EMP bugs, the
  1.02× identity probe), and II.5's vacuous-verification incident is the argument for
  doing it systematically.
- **[proposed] Close the disclosed untested path:** the `k == m` hull-terminal fallback in
  `empc_literature` (flagged in source since v2) — construct the unusual pi0/ROI
  combination that reaches it; one test.
- **[proposed] Property-based tests** (`hypothesis`) for the algebraic invariants now
  covered only by examples: monotone-transform invariance of ranking metrics,
  `realized_book_profit` additivity over disjoint masks, byte-determinism per seed.

## III.4 Priority

If only three run: III.2-1 (spaced-seed rerun — repairs the weakest published evidence),
III.2-2 (reveal-`u` ablation — upgrades the most-staked claim from correlation to
mechanism, and is v4-shaped anyway), III.3-doc-number-gate (compounds forever). None of
these blocks anything already published: the published claims survive the verification
pass as stated; this list is where the *next* increment of rigor lives.

*End of Part III. Dated snapshot of the post-release tree at `416e3a2`; supersede with a
new dated part, never edit.*
