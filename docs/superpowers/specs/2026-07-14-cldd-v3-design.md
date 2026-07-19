# CLDD v3 — FeedbackLoop Profit Decomposition

**Status:** Rev 2 — revised against operator review; implementation contract
**Date:** 2026-07-14 (rev 2, same day)

**Rev 2 changes:** decision 6's alarm-count provenance pinned to explicit run keys and the
HEAD blob (review challenge resolved — the 9/12 + 3/12 counts confirmed; the challenger's
6/6 reading came from pooling severities); H3a policy-book secondary added to §3 (separates
the learning benefit from the label bill); §4 gains a pilot slice, a runtime budget, and an
explicit parallelism policy; §10 gains a pilot gate so the H4 identity can fail in minutes,
not after the full matrix.
**Rev 2.1 amendment (2026-07-19, during implementation):** the §10.3 pilot gate fired exactly
as designed — H4 broke at max abs error ~2e-4 against the 1e-6 tolerance on the first pilot
run. Root cause: decision-5 day-90 imputation prices a slice at *that slice's own* body-mean
λ, making book P&L non-additive across slices — §1.1's "reuses `realized_profits` on the
funded rows" and §3's "arithmetic identity" clause were in contradiction, and the identity
clause is the normative one. Resolution: `realized_book_profit` prices per-row profits over
the **full cohort** (imputation basis = the cohort's body defaulters — a planted, funding-
invariant property) and sums the funded rows. §1.1's funded-rows clause is revised
accordingly; `realized_profits`/`loss_fractions` (v2 surfaces) are untouched; H4 is exact by
construction; the basis and the identity are both pinned by tests
(`test_h4_additivity_identity_across_book_and_explored_slice`,
`test_day_ninety_imputation_basis_is_cohort_not_funded_slice`). Tolerance was **not**
loosened.

**Rev 2.2 amendment (2026-07-19, during the first full sweep):** §10.5 fired on the full
matrix — H4 max abs error exactly 0.0001 at every severity — while the identity is exact
in-process (raw error ≤ 1.04e-17, measured at a fresh seed) and the error distribution over
all 825 frozen generation-rows is {0 × 626, exactly-1e-4 × 199}: pure round(4) quantization
of the stored columns, not a leak. The §4 round(4) convention put the identity-bearing
columns below the gate's own 1e-6 tolerance. Resolution: `book_profit` and `explored_profit`
are stored at round(10) in the sweep CSV (all other float columns keep round(4)); `H4_TOL`
is **unchanged** — precision raised, tolerance never loosened. The pilot's earlier pass was
12-row cancellation luck; the full-matrix gate did its job.

**Repo:** `closed-loop-default-detection`, version 0.2.0 → 0.3.0
**Builds on:** `docs/superpowers/specs/2026-07-13-cldd-v2-emp-design.md` (Rev 3) and
CHANGELOG [0.2.0]. The independent-assessment verdicts this design answers are recorded
in `docs/assessment.md` Part II (2026-07-14; in the working tree pending operator commit
at the time of writing).

v3 prices the **dynamic** regime the v2 EMP layer never touched: `FeedbackLoop`, where the
model's own approvals create its next training set. The deliverable is a decomposition of
realized book profit into a policy-switch share, a feedback-accumulation share, and an
exploration-recovery share — each a pre-registered, falsifiable hypothesis — plus the
measured answer to the v2-banked question ("does profit degrade before declined-ECE alarms
fire?"), whose premise this session found to be degenerate.

## Decision record (forks closed during brainstorming, 2026-07-14)

1. **Scope: option B (FeedbackLoop trajectory) is v3's core.** Option A (the
   `unobserved_strength` axis) and option C (structured selection) are deferred, named in
   §9. Operator decision against the session's initial A recommendation; not to be
   relitigated.
2. **System under study: passive pricing.** The deployed policy stays exactly what
   `FeedbackLoop` ships today — rank-based top-k at fixed `approval_rate`
   (`feedback.py:113-126`). v3 prices that trajectory; it never changes a funding
   decision. EMP/profit remain **reporting-only** (v2 decision 1 extends unchanged).
   The endogenous-EMP-cutoff experiment is out of scope (§9) — it would make the cutoff
   part of the selection mechanism under study and confound the headline.
3. **"Profit" in every headline = realized funded-book P&L** — actual profit of the rows
   the policy funded, per-row planted timing, v2 §1 economics. It is not an EMP
   functional: no cutoff optimization, no prior — so it dodges both the EMPC mispricing
   (measured 3.0× on ROI in v2) and the Jensen gap. Declined-pool `emp_h` is reported as
   the supporting blind-spot series; `empc` is a continuity column **only, never in a
   hypothesis or headline**.
4. **Label inheritance:** every quantity above consumes planted, risk-unlinked default
   timing, so the v2 §2 label — *verified experiment, not verified result* — attaches to
   the **whole trajectory**, in every headline sentence, README table, and CSV column doc.
   Choosing realized P&L removes the prior-mispricing and Jensen objections; it does not
   launder the timing label.
5. **Three arms** (minimal sufficient decomposition of the trajectory's causes):
   - **treatment** — model policy + retrain each generation (today's `FeedbackLoop`,
     byte-identical behavior);
   - **frozen** — model policy, generation-0 model deployed unchanged forever
     (isolates feedback accumulation);
   - **prior** — prior-policy funding every generation, retrain each generation
     (iid noise floor / static analog).
   The fourth cell (prior + frozen) is near-redundant with the prior arm and is not run.
   Arms share cohorts within (seed, severity) by construction — same generator seeds —
   so all contrasts are **within-seed paired series**, and all statistics are paired.
6. **Claim shape: signed decomposition, not event ordering and not occupancy counts.**
   Session-measured fact (recomputed 2026-07-14 from the committed
   `feedback_generations.csv` at HEAD, blob `204379f`, disk-identical; 72 rows = **12 runs
   keyed (seed, selection_severity, exploration_rate)** — 3 seeds × severity {0.4, 1.0} ×
   eps {0, 0.05} — × 6 generations): the declined-ECE alarm (> 0.10) fires at generation 1
   in 9/12 runs and generation 2 in 3/12 (the three severity-1.0, eps-0 runs) —
   **12/12 immediate**, then bounces noisily around an elevated level. Any recount must
   group on the full run key; pooling severities collapses the 12 runs to 6 apparent runs
   and hides the generation-2 firings behind their severity-0.4 partners. Consequences: (a) a "profit degrades *before* the
   alarm" event-ordering headline has a degenerate premise and is rejected; (b) a sign-only
   2×2 occupancy claim was rejected as statistically fungible (no sharp null; its alarm
   axis is ~constant anyway). v3's headline is H1–H3 of §3, each with a direction, a null,
   and an effect floor. The alarm immediacy is itself **reported as the measured answer to
   the banked question**, re-verified at 25 seeds (§5).
7. **Seed set: new, spaced — the inherited 25-seed set is rejected for this sweep.**
   A 12-generation feedback run at base seed *s* consumes generator seeds *s..s+11*; the
   inherited set has gaps < 8, so neighboring runs would share up to half their cohorts
   byte-identically — and H1–H3's binomial/Wilcoxon nulls assume independent replicates.
   The comparability argument does not transfer: `frontier_sweep.csv` is the static loop,
   a different system with different seed consumption; no row-level pairing exists to
   preserve. v3 seeds: **{1000 + 16·i : i = 0..24}** (1000, 1016, …, 1384), spacing 16 ≥ 12.
8. **Sweep matrix: full factorial** (operator decision over the trimmed variant):
   25 seeds × severity {0.2, 0.4, 1.0} × eps {0, 0.05} × arms {treatment, frozen, prior}
   × 12 generations = **450 runs**. The eps grid on the frozen arm buys the §3 negative
   control H4; on the prior arm it reproduces the static exploration lever as a
   descriptive baseline.
9. **Confirmatory severity is 0.4** (the committed feedback world and published-frontier
   severity). H1–H3 are tested confirmatorily at severity 0.4 only, Holm-corrected;
   severities 0.2 (the static median frontier) and 1.0 are **pre-registered replication
   panels** — same statistics, computed and published, labeled secondary. This keeps the
   confirmatory surface at three tests instead of nine.

## 1. Core module changes

### 1.1 `cldd/emp.py` — one additive helper

```
def realized_book_profit(y_true, default_day, requested_amount, funded,
                         economics=None) -> float | None
```

- Reuses `realized_profits` (already built in v2 for exploration pricing) on the funded
  rows; day-90 rows take the decision-5 mean-body imputation with the tested λ = 1
  empty-body fallback. Returns `None` when timing columns are absent (flat cohorts) —
  mirrors `emp_harness`. **SCM-only, like everything in v3.**
- **Units:** total realized profit of funded rows ÷ (n_applicants × mean
  `requested_amount` over the **full cohort**) — profit per applicant as a fraction of
  cohort mean exposure. Extends v2 decision 6; the full-cohort denominator (not
  funded-only) makes arms with different funded counts comparable and keeps paired
  differences well-defined.
- Pure numpy, zero RNG, deterministic.

### 1.2 `cldd/feedback.py` — two additive flags, byte-exact defaults

- `FeedbackLoop(..., retrain: bool = True, policy_mode: str = "model")`.
  - `retrain=False`: the generation-0 model (trained on prior-funded rows) is deployed
    unchanged for all subsequent generations. **Exploration starts at generation 1 in
    this arm** (generation-0 training is identical at every eps): with retraining off,
    gen-0 exploration would contaminate the one model ever trained, and the H4 identity
    (§3) requires the deployed model to be eps-invariant. Explored rows from gen 1 on
    still fund (they enter the book and its P&L) but no training ever consumes them.
  - `policy_mode="prior"`: every generation funds via the cohort's own prior-policy
    `approved` column; the model is trained each generation (for its metrics) but never
    makes a funding decision. `policy_mode="model"` is today's behavior.
  - Validation: unknown `policy_mode` raises `ValueError`; `retrain=False` with
    `policy_mode="prior"` is allowed but unused by the sweep (near-redundant cell).
- `GenerationResult` gains `book_profit: float | None` and `explored_profit: float | None`
  (realized P&L of the explored slice alone, **same full-cohort denominator as
  `book_profit`**; 0.0 when nothing explored, `None` without timing). Declined-side
  `declined_empc` / `declined_emp_h` already flow through `LeverMetrics` since v2 — v3
  *writes them out* (the two values; the `*_fraction` fields stay on `LeverMetrics` and
  off the sweep CSV), it does not recompute them.
- **Hard gate:** with default flags, `run()` output is byte-identical to current master —
  the RNG stream layout (`seed + generation` cohorts and training, the
  `EXPLORE_STREAM_FEEDBACK` stream) must not change. Regression-tested (§6).

## 2. What is NOT changing

Loop control, the static `SelectiveLabelsLoop`, `emp.py`'s two EMP entry points, the
generators and their RNG streams, all committed v1/v2 artifacts and headline claims, the
frozen flat byte-identity baseline, `POLICY_PD_THRESHOLD` handling, and the fidelity gate.
`FeedbackLoop` defaults produce byte-identical results.

## 3. Pre-registered hypotheses

All statistics are computed over **generations 1..11** (generation 0 is shared setup in
every arm), as within-seed paired differences at matched (severity, eps), then aggregated
across the 25 seeds.
Per-seed statistic: the mean over generations 1..11 of the per-generation paired
difference in `book_profit`.

| ID | Contrast (per seed, severity 0.4) | Direction | Role |
|----|-----------------------------------|-----------|------|
| H1 | treatment(eps 0) − frozen(eps 0) | < 0 (accumulation costs money) | confirmatory |
| H2 | frozen(eps 0) − prior(eps 0) | < 0 (policy switch costs money) | confirmatory |
| H3 | treatment(eps .05) − treatment(eps 0) on `book_profit` | > 0 (exploration buys profit back, net of the label bill) | confirmatory |
| H3a | same contrast on `book_profit − explored_profit` (policy book only) | > 0 (learning improves the policy-funded book) | secondary |
| H4 | frozen(eps .05) − frozen(eps 0) | = Σ explored_profit exactly (identity) | integrity control |

H3 nets two opposing effects: the explored rows' own P&L (the label bill — plausibly
negative) and the better-model effect on what the policy funds. H3a strips the explored
slice's P&L out (both columns are in the CSV; zero extra runs), leaving the pure learning
effect on the policy book — in the treatment arm the policy funding itself differs across
eps, so H3a isolates exactly that. The pair distinguishes **"stabilizer that isn't worth
its cost"** (H3 fails, H3a passes) from **"no stabilization at all"** (both fail) — the
distinction v3 exists to make. H3a is pre-registered secondary: same paired tests, own
p-value reported, outside the Holm family and never a headline on its own.

- **Tests:** exact sign test (`scipy.stats.binomtest`) and Wilcoxon signed-rank
  (`scipy.stats.wilcoxon`), both one-sided in the stated direction; **Holm correction
  across H1–H3 at α = 0.05** (both tests must clear it — the sign test is primary, the
  Wilcoxon supporting). H4 is an integrity control, not a discovery claim: because the
  frozen arm's deployed model and policy funding are eps-invariant by §1.2, the paired
  difference must equal the explored slice's own `explored_profit`, summed, to float
  tolerance — an arithmetic identity that verifies the flags actually freeze the model
  and exploration never leaks into training or policy. Its sign (the measured P&L of
  exploration in the no-learning limit) is reported descriptively, not predicted: whether
  random declines lose money depends on the declined pool's base rate vs the loan's
  break-even, and pretending to know the sign in advance would be a fake hypothesis.
- **Effect floor (pre-registered formula, not a constant):** for each severity, pool the
  absolute generation-to-generation `book_profit` differences within every prior-arm
  eps-0 run (11 successive diffs × 25 seeds); the floor is the **median** of that pool —
  the prior arm's own noise scale. A hypothesis is *confirmed* only if it clears Holm-α
  **and** |median across-seed paired deficit| ≥ floor. Between α-significant and
  floor-clearing lies "detected but below the noise floor" — reported as such, never as a
  headline.
- **Reported, v2-style:** median paired deficit, k/25 sign counts, and the full per-seed
  distribution in the CSV. **No single-seed number is ever quoted, including as a teaser**
  (repo-wide rule from v2).
- Severities 0.2 and 1.0: identical machinery, published as replication panels, labeled
  secondary (§ decision 9).

## 4. Sweep — `scripts/run_feedback_sweep.py`

- Matrix per decision record 7–8: seeds 1000..1384 step 16 × severity {0.2, 0.4, 1.0} ×
  eps {0, 0.05} × arms {treatment, frozen, prior}, `n_generations=12`, `generator="scm"`
  → 450 runs, 5 400 generation rows.
- **One subprocess per run** (the `run_sweep_25_driver.py` discipline — two evaluations in
  one process have exhausted memory before). A run's key is (seed, severity, eps, arm).
  **Output is shard-per-run**, `artifacts/feedback_sweep_parts/<key>.csv`, concatenated
  into the final CSV in deterministic key order only when all shards exist — no concurrent
  appends to a shared file. Resume = skip existing shard keys.
- **Parallelism policy (explicit):** the subprocess-per-run discipline exists for
  per-process memory accumulation, not machine RAM, so parallel workers are allowed —
  `--workers N`, default 4, each run still its own subprocess; shards make this
  concurrency-safe by construction.
- **Runtime budget:** one run ≈ 12 SCM cohorts + up to 12 trainings + 12 propensity fits
  ≈ 1.5–2.5 min → the 450-run matrix is ~11–19 h sequential, ~3–5 h at 4 workers. Stated
  so the burn is a decision, not a surprise.
- **Pilot slice before the matrix (`--quick`):** seed 1000 × severity 0.4 × all six
  (arm, eps) cells = 6 runs (~15 min). `feedback_sweep_stats.py --pilot` runs on the pilot
  shards and **asserts the H4 identity to float tolerance**; the full matrix does not
  launch until the pilot gate (§10.3) is green. The pilot exists to fail mechanically in
  minutes, not after the burn; its numbers are never quoted (single-seed rule).
- Output: **new artifact `artifacts/feedback_profit_sweep.csv`** — one row per generation:
  `seed, selection_severity, exploration_rate, arm, generation, policy, funded_rate,
  funded_default_rate, book_profit, explored_profit, declined_ece, declined_mean_pd,
  declined_base_rate, all_ece, declined_empc, declined_emp_h, diag_propensity_auc,
  diag_ess_ratio, diag_below_floor, diag_flagged, n_explored, explored_defaults`.
  Rounding follows `run_feedback.py`'s existing round(4) convention.
- The committed `feedback_generations.csv` (6 generations, 3 seeds) is **not** the sweep's
  output file and is never appended to.

## 5. Analysis — `scripts/feedback_sweep_stats.py`

Separate script so every published number **recomputes from the committed CSV** (repo
discipline): reads `feedback_profit_sweep.csv` (or the pilot shards under `--pilot`, asserting the H4
identity and exiting non-zero on failure) and computes the §3 statistics (paired deficits
for H1–H3 and H3a, sign counts, Holm-adjusted p-values, the noise floor, the H4 identity
check),
the **T_ece distribution** (first model generation with `declined_ece >
TARGET_DECLINED_ECE` per treatment run — the 25-seed re-verification of the alarm-immediacy
finding), and emits `artifacts/feedback_sweep_stats.csv` plus an ASCII summary (Windows
cp1252 console — no non-ASCII in `print()`).

Registered-defect note carried in the output and docs: the 0.10 threshold is the loop's
operative alarm but an arbitrary constant, and 10-equal-width-bin ECE is a noisy control
statistic (assessment defect 5). v3 uses the alarm because it is what the harness *does*;
it does not defend the constant.

## 6. `run_feedback.py` and the artifacts invariant

The committed `artifacts/feedback_generations.csv` is handled by the v2 §10.4 precedent:
`run_feedback.py` gains the new columns (`book_profit, explored_profit, declined_empc,
declined_emp_h`), the CSV is regenerated once, and a gate asserts **every v1 column of the
regenerated file equals the committed values exactly** (17 existing columns, additive
columns only). Since `FeedbackLoop` defaults are byte-exact and the new columns are pure
reporting on the same in-process state, this must hold; failing it means §1.2 broke the
stream layout.

## 7. Determinism and testing

No new RNG anywhere: `realized_book_profit` is arithmetic over existing columns; the two
`FeedbackLoop` flags only *select* among existing streams (frozen skips training calls;
prior uses the cohort's `approved`). New tests:

- `realized_book_profit`: hand-computed miniature cohorts — all-good book, all-default at
  day 0 / day `TERM_DAYS` / day 90 (imputation + empty-body λ = 1 fallback), mixed funded
  mask, full-cohort-denominator arithmetic, flat cohort → `None`.
- Flag semantics: frozen arm calls `train_pd_model` exactly once (call-count via
  monkeypatch); prior arm's funding equals `cohort["approved"]` every generation;
  invalid `policy_mode` raises.
- **Default-path byte-identity regression:** `FeedbackLoop().run()` under fixed seed
  serializes (sha256) identically before/after v3 — protects every committed feedback
  number.
- §3 statistics on a hand-built fixture CSV: known signs, known Holm ordering, floor
  arithmetic, H4 consistency check.
- Cross-process float determinism for `realized_book_profit` (sha256, existing
  discipline).
- The frozen flat byte-identity baseline and the full v2 suite: green, untouched.

## 8. Documentation

- **README:** a "Pricing the feedback loop" section — the H1–H3 verdicts as measured
  (medians + sign counts + label), the alarm-immediacy finding as the answer to the
  banked question, the H4 control, and the timing label verbatim in the same block.
  Numbers recompute from `feedback_profit_sweep.csv` via §5.
- **Docs site:** mechanics in `docs/how-it-works.md` (arms, pairing, units), gates and
  repro in `docs/validation.md`; **no mermaid fences in `docs/*.md`** (`-W` build);
  `docs/configuration.md` knob table gains the two flags; `automodule` already covers
  `cldd.emp`/`cldd.feedback`.
- **CHANGELOG [0.3.0]:** results written only after the sweep runs; sweep-first
  discipline — the section carries distributions, never a single seed.
- **`docs/assessment.md`: untouched** (dated snapshot; Part II is the operator's pending
  commit and stays exactly as written).

## 9. Out of scope (named, deliberate)

- Endogenous EMP-cutoff funding policy (decision record 2's rejected alternative).
- Option A — the `unobserved_strength` × severity frontier surface (deferred, not
  dismissed: still the assessment's staked "cheapest most-valuable move"; a natural v4
  alongside C).
- Option C — structured/segmented selection policies.
- Label accumulation across generations (the module's isolation design choice stands).
- Flat-generator default timing (byte-identity baseline forbids it).
- Any EMPC-based hypothesis or headline (continuity column only).
- Changing `TARGET_DECLINED_ECE`, the ECE binning, or the model family (registered
  defects, out of this scope).

## 10. Verification gates before merge

1. Full test suite green under pins, including the §7 default-path byte-identity
   regression and the untouched flat baseline.
2. §6 column-identity gate: all 17 v1 columns of the regenerated
   `feedback_generations.csv` byte-equal to committed values.
3. **Pilot gate:** the `--quick` slice (6 runs) completes and
   `feedback_sweep_stats.py --pilot` passes the H4 identity to float tolerance —
   **before the full matrix launches.**
4. 450/450 sweep runs complete (driver reports zero missing shard keys);
   `feedback_sweep_stats.py` recomputes every README/CHANGELOG number from the CSV.
5. H4 integrity identity holds to float tolerance on the full sweep — a failed control
   **blocks publication of H1–H3** until explained.
6. `sphinx -b html -W` clean; configuration table updated.
7. Version bump to 0.3.0, pins unchanged (`scikit-learn==1.9.0`, `numpy==2.4.6`).
8. Every headline sentence carries the planted-timing label; no single-seed quotation
   anywhere in README/CHANGELOG/docs.

All git commits are run by Hossain; the implementation session operates from this spec as
contract.
