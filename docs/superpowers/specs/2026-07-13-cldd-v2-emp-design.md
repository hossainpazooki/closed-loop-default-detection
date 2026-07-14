# CLDD v2 — Expected Maximum Profit Measurement Layer

**Status:** Rev 2 — revised against code review; implementation contract
**Date:** 2026-07-13 (rev 2, same day)
**Repo:** `closed-loop-default-detection`, version 0.1.0 → 0.2.0

**Rev 2 changes:** §2's fitted-vs-cosmetic question resolved from code inspection (outcome: conditionally cosmetic — labeling path applies); day-90 λ convention closed (decision 5); EMP units pinned (decision 6); §5 corrected (the 25-seed set is the counterfactual sweep's, `TRAIN_SEED_OFFSET` is loop-internal, subprocess discipline named, seed-correlation caveat added); CSV column-identity gate added (§10.4); all names updated for the lineage rename (`run_loop.py`, `loop_frontier*`, `docs/assessment.md`); §8 housekeeping items marked done.

## Decision record (forks closed during brainstorming + review)

1. **Role of EMP:** reporting axis only. ECE remains the sole loop-control metric; EMP prices the frontier. Loop pass/fail, severity escalation, and frontier logic are untouched.
2. **Parameter sourcing:** both variants, side by side — literature-standard EMPC (benchmark-comparable) and harness-derived EMP (parameters true by construction where the generator constructs them — see decision 5 for the one stated imputation). Material disagreement between the two is itself a reportable finding.

   *Rev 3 correction (2026-07-14, measured).* Rev 2 claimed harness EMP is "mathematically EMPC with an empirical h(λ)". **That was overstated — retracted.** λ-independence from score holds (§2), but the two are not the same functional: EMPC is `E_λ[max_cutoff profit]` (expectation *of* the maximum, integrating LGD uncertainty) while harness EMP is `max_cutoff[realized profit]` with per-row planted λ (maximum *of* the realized). By Jensen these differ even under an identical h(λ). They also differ in ROI and in h(λ) itself.

   **The disagreement is now measured, and it is the predicted finding:** on the SCM cohort (seed 42, severity 0.6) the literature prior assumes **ROI = 0.2644 vs this loan's actual 0.0875** (3% origination fee + 5.75% over a 60-day term) — a 3.0× overstatement of the return — and places **55% of defaults at full recovery where the harness plants 1.2%** (prior mean λ = 0.275 vs harness 0.419). Consequence: across the severity grid the two variants move in **opposite directions** (SCM: EMPC 0.0217 → 0.0420 rising, EMP_h 0.0387 → 0.0024 collapsing). The convenience prior misprices this loan structure exactly as decision 2 anticipated; this is a headline v2 result, not an implementation defect.
3. **Headline statistic:** raw EMP against planted labels. No oracle-ranking regret. Raw EMP moves with world hardness even for a perfect model; cross-severity EMP deltas are not pure model signal — documented reading caveat (§8), not a solved problem.
4. **Generator split:** the flat generator (`synthetic.py`) has no default timing and its frozen byte-identity baseline (`tests/test_loop_scm.py::_FLAT_FROZEN_ROUNDS`) forbids RNG-stream changes. Flat cohorts get literature EMPC only; harness-derived EMP is SCM-only.
5. **Day-90 point mass (rev 2, closed at review):** ~22.5% of SCM defaulters carry `days_to_default = 90` (`scm.py:983`, the post-term "trigger 3"; the smooth body lives on [3, 60], (60, 90) is empty). The draws-through-*t* mapping is undefined past `TERM_DAYS = 60` — naively it yields λ = 0, making a quarter of defaults costless. **Convention:** day-90 rows are priced at the **cohort's mean body λ** (mean loss fraction over that cohort's defaulters with t ≤ 60) — a stated, deterministic imputation for a trigger whose intra-term payment history the generator does not model. Alternative λ = 1 rejected (overstates losses for an unmodeled trigger). Consequence: the "true by construction" claim holds for the ~77.5% body and is a **stated imputation** for the day-90 mass — this appears verbatim in the CSV column docs and README.
6. **Units (rev 2, closed at review):** both variants report `emp` as **expected profit per applicant as a fraction of mean per-loan exposure**. EMPC is amount-fraction-native (its parameters are rates); harness EMP computes dollars from per-row `requested_amount`, then normalizes by the cohort's mean `requested_amount`. Without this the side-by-side in decision 2 compares incommensurable numbers.
7. **Names:** all v2 work builds on the post-rename tree — `scripts/run_loop.py`, `artifacts/loop_frontier*.{csv,png}`, `docs/assessment.md`. The CHANGELOG `[Unreleased]` section already carries the renames; v2 ships them inside 0.2.0.

## 1. Core module — `cldd/emp.py`

Pure numpy, zero RNG. No new dependencies (scipy is already a dependency via `scm.py`, but `emp.py` needs nothing beyond numpy).

Shared result type:

```
@dataclass
class EMPResult:
    emp: float               # expected profit per applicant, fraction of mean exposure (decision 6)
    optimal_fraction: float  # fraction of the population the EMP-optimal cutoff APPROVES
    n: int
```

`optimal_fraction` direction: the literature's η is typically the fraction *rejected*; this codebase defines the approved fraction. The convention check is part of gate §10.1.

Two entry points:

- `empc_literature(y_true, scores, params) -> EMPResult` — Verbraken et al. EMPC closed form via the ROC convex hull. Deterministic; no sampling. `params` is a config-owned struct (§2), never inline constants.
- `emp_harness(y_true, scores, default_day, requested_amount, economics) -> EMPResult | None` — expectation using per-defaulter loss fractions from planted timing. Economics (all from `config.py`, formulas fixed here so implementation invents nothing):
  - exposure per row: `A = requested_amount` (**not** `prior_approved_amount`, which is NaN for declines by construction, `scm.py:663` — and explored/declined rows are exactly the rows EMP must price);
  - term finance rate: `r_term = APR * TERM_DAYS / 365`; origination fee `f = ORIGINATION_FEE_RATE`, collected up front (defaulters pay it too);
  - collections for a default at day t ≤ 60 (t draws collected, level daily draws of `A*(1+r_term)/TERM_DAYS`): `f*A + (t/TERM_DAYS)*A*(1+r_term)`;
  - per-row profit = collections − A; λ = −profit/A for defaulters; good loan (t = TERM_DAYS equivalent): profit = `A*(f + r_term)`;
  - day-90 rows: mean-body-λ imputation per decision 5;
  - returns `None` when the cohort lacks default-timing columns (flat cohorts).

Both functions consume `scores` as a ranking only — invariant to strictly monotone transforms (tested, §7). `emp_harness` must not use score values as probabilities anywhere (no PD-weighted expected-loss terms), or the invariance breaks.

## 2. Parameters and preconditions

**Literature side.** The EMPC prior constants — the h(λ) point-mass/uniform mixture parameters and the ROI constant — enter `config.py` only after verification against the Verbraken/Bravo/Weber/Baesens source, together with the `optimal_fraction` direction convention. No constant is written from memory. **Done 2026-07-13 (spike):** verified against EJOR 238(2):505-513 (Eqs. 13/15; h(λ) = p0·δ(0) + p1·δ(1) + (1−p0−p1)·U(0,1)) and CRAN `EMP::empCreditScoring` defaults (p0=0.55, p1=0.10, ROI=0.2644; `EMPfrac` = fraction excluded → `optimal_fraction` = 1 − it).

**Harness side — RESOLVED at review (was: precondition).** Code inspection of `scm.py:969-986` settles the fitted-vs-cosmetic question: `days_to_default` is drawn from two dedicated exogenous uniforms (`__survival_body__`, `__survival_mass__`), **independent of features, risk logit, and confounder given default status**. The marginal shape follows the survival spec (beta(2.2, 2.3) body on [3, 60] + 22.5% mass at 90) but is validated nowhere — `fidelity.py` has no survival coverage, and nothing outside `scm.py` consumes the column today. Verdict: **marginally spec-shaped, conditionally cosmetic.** Therefore:

- the labeling path applies: harness-EMP output is labeled as resting on timing that is planted but not risk-linked — *verified experiment, not verified result* — in README and CSV column docs;
- the claim "h(λ) is measured" is made only for the marginal (and only for the body; the day-90 mass is the decision-5 imputation);
- since λ ⊥ score, per-row λ adds no ranking-relevant heterogeneity — but this does **not** collapse harness EMP into EMPC-with-empirical-h(λ) (see decision 2's Rev 3 correction: different functional, different ROI, different h(λ)).

## 3. Loop and reporting integration

- `SubgroupMetrics` gains optional fields, `None` where inapplicable: `empc`, `empc_fraction`, `emp_h`, `emp_h_fraction`, plus `f1_emp_cutoff` (§6).
- `LeverMetrics` passes through the declined and all-population EMP fields, mirroring the existing `declined_*` / `all_ece` pattern (`correctors.py`).
- `score_pd_detection` computes EMP from the **same in-process scores** it already measures. No replay path, no post-hoc regeneration.
- `scripts/run_loop.py`: CSV gains the EMP columns; the plot gains an EMP-vs-severity panel alongside the ECE panel.
- Loop control (`control_metric`, `passed`, severity escalation, frontier) is logically unaffected — same decisions on same inputs.
- **Rev 2 — artifact reconciliation:** regenerating `artifacts/loop_frontier*.csv` with added columns touches committed evidence the README recomputes from. The reconciliation with the "never modify `artifacts/*.csv`" invariant is gate §10.4: **every v1 column of the regenerated CSVs must equal the committed v1 values exactly.** Since EMP is pure reporting on the same in-process scores, this must hold; it is also the check that operationalizes "EMP prices the frontier" being true by construction. (Precedent: the 2026-07-13 rename verified regenerated `loop_frontier.csv` byte-identical under pins.)

## 4. Exploration-lever profit accounting

`RoundResult.n_explored` and `explored_defaults` are currently unitless counts. v2 prices them with the §1 economics:

- `exploration_cost`: realized losses on explored defaults minus realized returns on explored non-defaults, exposure = `requested_amount` per row (§1). Loss per explored default uses the per-row planted λ where timing exists (SCM, incl. the decision-5 imputation for day-90 rows); on flat cohorts explored defaults are priced at λ = 1 — a stated, conservative convention, documented in the CSV column notes. Sign convention: positive = the exploration budget cost money net.
- Reported per round in `RoundResult` and the CSV. **Not** a gate input.

## 5. Frontier seed sweep

New script `scripts/run_frontier_sweep.py`: run `SelectiveLabelsLoop` across the existing 25-seed set and emit `artifacts/frontier_sweep.csv`, one row per seed: frontier severity, per-round declined ECE per lever, EMP columns, exploration cost.

**Rev 2 corrections to this section:**

- The 25-seed set is the **counterfactual** sweep's: {7, 13, 42, 101, 2026} from `scripts/run_seed_sweep.py` plus the 20 in `artifacts/run_sweep_25_driver.py`. Neither existing script runs the loop; this script is the first loop-level sweep.
- `TRAIN_SEED_OFFSET` disjointness is **internal to `SelectiveLabelsLoop`** (measure seeds `s+i`, train seeds `s+1000+i`) and needs nothing from the sweep. The discipline actually inherited from the existing sweeps is **one subprocess per loop run, resumable append** (two evals in one process have exhausted memory; `run_sweep_25_driver.py` is the pattern).
- **Correlation caveat (documented in the README table, not fixed):** loop seed *s* consumes generator seeds *s*..*s*+7, and the 25-seed set has gaps < 8, so runs share feature draws (same generator seed at different severities → identical features, different selection). No two runs duplicate a cohort (severity is iteration-locked), but the 25 rows are not fully independent. The set is kept for comparability with the committed counterfactual sweep; the caveat is named where the distribution is reported.

Reported: the frontier's seed **distribution** (min / median / max and full histogram data), and EMP-at-frontier spread. No core-module changes; script + CSV + README table only.

## 6. Retiring the arbitrary 0.5 threshold

`POLICY_PD_THRESHOLD = 0.5` is a placeholder with no economic justification (documented as diagnostic-only in `docs/configuration.md` as of 2026-07-13). v2 reports F1 at the EMP-optimal cutoff **alongside** the existing F1-at-0.5 (additive field `f1_emp_cutoff` next to `f1`). The 0.5 diagnostic is retained for continuity with v1 artifacts; its docstring gains a pointer to the EMP-cutoff column as the economically grounded alternative.

## 7. Determinism and testing

**Determinism guarantee.** `emp.py` consumes zero RNG: convex hull closed-form; harness expectation over columns already present in the cohort; the decision-5 imputation is a deterministic per-cohort mean. No Monte Carlo anywhere in v2. The frozen flat byte-identity regression stays green, unmodified.

**Test plan:**

- Hand-computed convex-hull cases: perfect ranking, random ranking, small ROC with known hull vertices, EMPC vs manual arithmetic.
- Invariants: monotone-transform invariance of the ranking input (both entry points); EMP within derivable bounds; a strictly better ranking never yields lower EMP on the same cohort.
- Degenerate harness cases, using the §1 formulas: all defaults at day 0 (λ = 1 + no draws, fee still collected); all at day `TERM_DAYS` (λ ≈ 0; profit = fee + full-term collections − principal); **all at day 90** (every row priced at the mean-body imputation — with an all-mass cohort the body is empty, so the imputation must have a defined fallback: λ = 1, tested).
- Exploration accounting: fixed miniature cohort, hand-computed `exploration_cost`, exposure from `requested_amount`.
- EMP-optimal-cutoff F1: agreement with a brute-force cutoff scan; `optimal_fraction` direction (approved, not rejected) asserted explicitly.
- Cross-process float determinism (sha256 over serialized outputs, matching existing discipline).
- Flat byte-identity regression: green, untouched.

## 8. Documentation

- **README:** what each EMP variant measures; literature-vs-harness disagreement framed as a parameter-prior finding (decision 2); the raw-EMP reading caveat (decision 3); the decision-5 imputation sentence; the frontier-distribution table with the §5 correlation caveat; exploration-cost column semantics; the §2 "verified experiment, not verified result" label.
- **Docs site:** EMP mechanics go in `docs/how-it-works.md` / `docs/validation.md` (plain MyST — **no mermaid fences in `docs/*.md`**, the `-W` build has no mermaid lexer); `cldd.emp` gets an `automodule` entry in `docs/api.rst`.
- **`docs/assessment.md`** (formerly `FABLE.md`): untouched until numbers exist. No claims ahead of measurement. It is a dated snapshot excluded from the Sphinx build.
- **Housekeeping — DONE 2026-07-13** (was: METHODOLOGY.md item, which turned out to be the sibling hackathon repo's file where the rationale already existed): the sklearn-only portability note landed in `docs/validation.md`; the `config.py` knob table in `docs/configuration.md` now covers the loan-economics constants v2 makes load-bearing; CLUE-lineage renames and the FABLE move are complete, gates green, committed.

## 9. Out of scope (named, deliberate)

- EMP as a gate or loop-control input, in any form.
- EMP-optimal-cutoff-driven approval policy (endogenous-cutoff redesign).
- Oracle-ranking profit regret.
- FeedbackLoop EMP trajectory across generations — the v3-shaped item.
- Adding default timing to the flat generator (byte-identity baseline forbids it).
- Fitting default timing to risk in the SCM (would change the SCM RNG stream and re-baseline the SCM artifacts; if ever done, it converts §2's label from "unfitted timing" to "measured h(λ|x)" — a v3-shaped upgrade, not a v2 item).

## 10. Verification gates before merge

1. EMPC prior constants **and** the `optimal_fraction` direction convention verified against the primary source before entering `config.py`. **Done 2026-07-13 (spike — see §2).**
2. §2 labeling implemented as specified (the inspection itself is done; the gate is that README + CSV docs carry the resolved outcome, including the decision-5 imputation sentence).
3. Full test suite green, including the untouched flat byte-identity regression.
4. **Regenerated `artifacts/loop_frontier*.csv`: all v1 columns exactly equal the committed v1 values** (additive columns only — this is the reconciliation with the artifacts invariant).
5. `sphinx -b html -W` clean with the new docs content; `docs/configuration.md` table extended with the EMPC param struct.
6. Version bump to 0.2.0 with pins unchanged (`scikit-learn==1.9.0`, `numpy==2.4.6`); the CHANGELOG `[Unreleased]` renames ship inside 0.2.0.

All git commits are run by Hossain; the implementation session operates from this spec as contract.
