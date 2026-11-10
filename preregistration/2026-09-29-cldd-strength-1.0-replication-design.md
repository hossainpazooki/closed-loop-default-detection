# CLDD strength-1.0 replication: pre-registration

*Ratified by the operator 2026-09-29. This file is the pre-registration. On the
operator's instruction of the same day ("move superpowers docs to briefs") it is
held outside the public repo, in the operator's briefs folder. It is fixed
before any fresh seed is run. How that is made publicly checkable is the
operator's open decision: commit this file, or commit its SHA-256 digest. The
analysis that judges the run is `scripts/strength_replication_stats.py` in the
`cldd` repo, at the commit named in the run record. Amendments are made by dated
revision, never by loosening a tolerance.*

## 0. Purpose

The README's v4 section says the "median frontier severity is **0.4** at every
strength up to 0.7 and moves to **0.2** only at strength 1.0, in both worlds".
The CHANGELOG calls this "observed post-hoc, a future pre-registration rather
than a confirmation". This spec is that pre-registration.

v4's four hypotheses compared strength 0 to the **default** strengths, and none
was confirmed. The contrast tested here, strength 0 against strength **1.0**,
is one v4 never registered. If it replicates, the finding sharpens from "the
confounder is not the cause" to "the confounder does not build the wall, and at
full strength it moves it".

## 1. What was seen before this was written

Pre-registration is only as good as its disclosure. Everything below was
computed on the **spent** seeds `{1000 + 16i}`, from the committed
`artifacts/surface_frontier.csv`, before the hypotheses were worded. None of it
is a result. No seed in `{5000 + 16i}` has been run.

| Contrast, strength 0 → 1.0, 25 spent seeds | Flat | SCM |
|---|---|---|
| Calibration error at severity 0.4: median change | +0.0443 | +0.0240 |
| Calibration error at severity 0.4: seeds rising | 24 | 23 |
| Calibration error at severity 0.2: seeds rising | 18 | 18 |
| Calibration error at severity 0: seeds rising | 11 | 12 |
| Frontier receded / advanced / tied | 20 / 0 / 5 | 14 / 0 / 11 |

| Dose, strength 0 → v, severity 0.4 | 0.2 | 0.4 | 0.55 | 0.7 | 1.0 |
|---|---|---|---|---|---|
| Flat: median change | +0.0013 | +0.0088 | +0.0226 | +0.0206 | +0.0443 |
| Flat: seeds rising | 13 | 18 | 19 | 22 | 24 |
| SCM: median change | −0.0003 | +0.0045 | +0.0061 | +0.0099 | +0.0240 |
| SCM: seeds rising | 12 | 16 | 15 | 18 | 23 |

Both floors in §3 were proposed **after** their authors had seen these figures.
On the spent seeds both worlds clear them: flat 0.0443 against a floor of
0.0331, SCM 0.0240 against 0.0126.

The overlap flag was also sized on the spent seeds, by re-running the 50
strength-0 runs with the diagnostic columns (the reruns matched the committed
rows on every calibration-error value, 193 of 193):

| Overlap flag, strength 0, spent seeds | Flat | SCM |
|---|---|---|
| Fired at the run's failing severity | 25 of 25 | 18 of 25 |
| Fired on a passing round | 1 of 75 | 0 of 68 |
| Failed at severity 0.4 with the flag clear | 0 | 7 |
| Median propensity AUC at severity 0.4, failing vs passing runs | no failing runs | 0.836 vs 0.832 |

The pilot gate (§6) has been run on spaced seed 1000 and prints round counts.
It touches no fresh seed.

## 2. Decision record

The operator's ruling, verbatim, 2026-09-29: **"1. yes 2. yes"**, in answer to
"Do you adopt the suggested rulings, with my two amendments?" and "On your yes,
I make the replication changes, update the spec, and hand you the spec commit to
push before anything runs."

The suggested rulings adopted, verbatim from the review they came from:

| Fork | Ruling |
|---|---|
| R1 Contrast | Strength 0 vs 1.0, as drafted |
| R2 Family | Both worlds, as drafted |
| R3 Seeds | `{5000 + 16i}`, as drafted |
| R4 Default cells | Expand to all six strengths |
| R5 Counterfactual leg | Out of scope, as drafted |
| R6 Home | Standalone spec, as drafted |
| R7 (new) Primary outcome | Calibration error at severity 0.4; frontier becomes a secondary family |
| R8 (new) Diagnostics | Write the four diagnostic columns |
| R9 (new) Seed guard | Check consumed spans, not base seeds |

On the R7 floor the review suggested "the distance from the strength-0 median to
the 0.10 target, measured on the fresh seeds in each world". On R8 it suggested
"a pre-stated reading rule, outside the confirmatory family. If the flag is
clear at the failing severity on most strength-0 seeds, the overlap explanation
is withdrawn".

The two amendments adopted with them, verbatim:

1. "I recommend the floor be the larger of the two, per world. The stats script
   should also fail closed if the strength-0 median is already at or over the
   target, because the distance would then be zero or negative." The two are the
   target distance and the noise measured at severity 0.
2. "I recommend stating two reads in the spec, both descriptive: Across
   severities: the rule as suggested. It can withdraw the overlap explanation
   and cannot confirm it. Within severity 0.4: whether the diagnostics separate
   failing runs from passing ones."

**Two implementation decisions are not operator rulings** and are reviewable
before the run:

- A loop run that stopped before severity 0.4 has no calibration error there.
  Its pair is excluded and counted. A world with fewer than 20 of 25 pairs is
  unevaluable. The exclusion biases against the hypothesis, because a run that
  stops before 0.4 is a run calibration already left. On the spent seeds all 25
  pairs exist in both worlds.
- "Most" in the reading rule is 13 or more of 25 seeds.

## 3. Pre-registered hypotheses

Per seed, world `w`, confounder strength `v`:

- `E_w(v)` = declined-subpopulation ECE of the loop's control lever at severity
  0.4. Under the published configuration (`improve_mode="both"`, exploration 0)
  the control lever is the IPW reweight; the column is `reweight_declined_ece`.
- `F_w(v)` = the loop's frontier severity. A run that never passed is encoded
  −0.2, as in v4.

**Primary family** (Holm, m = 2, α = 0.05; one-sided exact sign test AND
one-sided Wilcoxon on the paired differences; both must clear, plus the floor):

- **H-R1f:** `E_flat(1.0) − E_flat(0.0) > 0`.
- **H-R1s:** `E_scm(1.0) − E_scm(0.0) > 0`.
- **Floor**, per world: the median paired difference must be at least the larger
  of (a) the **target distance**, `0.10 − median E_w(0.0)`, and (b) the **noise
  scale**, the median absolute paired difference in the same ECE at severity 0
  between strength 1.0 and strength 0. At severity 0 selection is random, so
  strength cannot act through selection and that contrast measures noise. Both
  are measured on the fresh seeds.
- **Unevaluable**, which blocks publication: `median E_w(0.0) ≥ 0.10`; or fewer
  than 20 pairs.

**Secondary family** (its own Holm, m = 2, same tests):

- **H-R2f:** `F_flat(0.0) − F_flat(1.0) > 0`. Floor: one severity step, 0.2.
- **H-R2s:** `F_scm(0.0) − F_scm(1.0) > 0`. Same floor.

Stated before the data: on the spent seeds the SCM frontier contrast has a
median exactly on its floor, with 14 of 25 seeds receding. It can miss on fresh
seeds even if the effect is real. That is why it is secondary.

**Falsification statement.** Each world is reported on its own primary verdict.
The README keeps "in both worlds" only if H-R1f and H-R1s are both confirmed. A
world that fails is reported as not replicated, in the same change. A secondary
verdict never rescues a primary one.

**Descriptive, no verdicts:**

- The dose response: the `E` contrast against strength 0 at each of the five
  other strengths, per world.
- The frontier distribution per cell.
- **Overlap flag, across severities, strength 0.** How often the flag fired at a
  run's failing severity. Reading rule: if the flag is clear at the failing
  severity on 13 or more of the 25 strength-0 seeds in a world, the overlap
  explanation is withdrawn for that world before any document publishes it.
  This read can withdraw the explanation and cannot confirm it, because the
  flag and the failure both follow severity.
- **Overlap diagnostics, within severity 0.4, strength 0.** Whether propensity
  AUC, effective-sample-size ratio and clip-floor share separate failing runs
  from passing ones: medians per group and a Spearman correlation against `E`.
  No threshold is registered. Separating overlap from severity needs an
  intervention on selection, which is a different experiment.

## 4. Sweep: `scripts/run_strength_replication.py`

Strengths `{0.0, 0.2, 0.4, 0.55, 0.7, 1.0}` × `{flat, scm}` × 25 fresh seeds
`{5000 + 16i, i = 0..24}` = **300 loop runs**, written to
`artifacts/strength_replication_frontier.csv`. The schema is the
`surface_frontier.csv` schema plus `propensity_auc`, `ess_ratio`,
`unfunded_below_floor`, `diag_flagged`. One subprocess per run, sequential,
resumable, ASCII stdout. Measured 2026-09-29: 8–15 s per run.

The child code is the v4 surface child with one block inserted, the four
diagnostic columns. A test asserts that removing the block gives back the v4
child byte for byte. No `src/` change.

**Seed disjointness.** A loop run at seed `s` consumes `s..s+7` and
`s+1000..s+1007`. Every committed artifact's seeds are at or below 2026, so
their runs consume nothing at or above 3034. The fresh set consumes 5000–5391
and 6000–6391. Spacing 16 exceeds the within-run span.

## 5. Analysis: `scripts/strength_replication_stats.py`

Recomputes every figure from the artifact and writes
`artifacts/strength_replication_stats.csv`. The frontier extraction, the
hypothesis row, the never-passed encoding and the statistics primitives are
imported from `scripts/surface_stats.py`. Exits non-zero on a missing cell, on
an unevaluable family, or on any row whose run consumed a seed a committed
artifact consumed. That guard checks the consumed span, not the base seed.

## 6. Integrity and testing

- **Pilot gate before the matrix, on spaced seed 1000 only.** The driver's rows
  at strengths 0 and 1.0, both worlds, must be string-equal on every shared
  column to the committed `surface_frontier.csv`; the four diagnostic columns
  must be present and non-empty; each run must finish inside 60 s.
- **No byte-identity embed gate on the matrix.** Fresh seeds have no committed
  reference. The pilot's byte-match ties this run to the observation's code and
  build.
- **Unit tests:** `tests/test_strength_replication.py`, 31 tests.
- All existing gates hold untouched.

## 7. Verification gates before any document quotes a figure

1. Full suite green under the pins.
2. Pilot gate passed before the matrix launched; its output recorded.
3. 300 of 300 runs present; no run consumed a spent seed.
4. `strength_replication_stats.py` exit 0.
5. Doc-number gate passes with the new claims registered; hash manifest
   re-pinned for the two new artifacts; docs build clean.
6. Independent skeptic pass on the verdicts before any document update.

## 8. Out of scope (named, deliberate)

- The counterfactual gap leg.
- Strengths above 1.0, or a finer grid between 0.7 and 1.0.
- Reveal-`u` at strength 1.0: the follow-up if this replicates.
- Segmented selection: its own spec, held until after the essay, to be run at
  strength 0.
- Any change to `src/`, to the severity walk, to `TARGET_DECLINED_ECE`, or to
  any committed artifact.
