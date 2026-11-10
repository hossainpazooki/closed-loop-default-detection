# CLDD Option C — segmented selection at strength 0: pre-registered design

*Frozen 2026-11-03. This file is byte-frozen once its SHA-256 is published in the
repository's `PREREGISTRATION.md`. It is held outside the repository. Rulings F1 to
F8 were taken by the operator on 2026-09-29 ("1. yes 2. yes" to the suggested
rulings with the drafter's two amendments); this document records them and the
design that follows from them. Nothing below has run on a confirmatory seed under
this design except the pilot gate on seed 1000, disclosed in section 7.*

## 0. Purpose

v4 turned the confounder dial and the wall did not move: at strength 0, with
nothing hidden, the flat frontier sits at 0.4 on 25 of 25 seeds. The strength-1.0
replication then showed that at full strength the confounder moves the wall, in
both worlds, on fresh seeds. What builds the wall at strength 0 is still untested
by intervention. The leading candidate is an overlap wall: at high severity the
selection is near-deterministic in the risk score, so the declined pool has no
funded counterparts.

Severity cannot test that candidate, because it moves two things at once: how much
of the selection is hidden, and how much overlap survives. A segmented policy
destroys overlap in an observable, at a fixed severity, with nothing hidden. If the
wall is an overlap wall, removing overlap by hand should reproduce it.

Second target: the observable positivity flag. Both worlds were measured under one
global cutoff. A segmented policy is the first selection structure that claim has
not seen.

## 1. Rulings in force

| Fork | Ruling (2026-09-29) |
|---|---|
| F1 Version | Separate release, after the essay |
| F2 Legs | Frontier only |
| F3 Primary attack feature | `aggregate_credit_utilization`, high end |
| F4 Depths | {0.0, 0.5, 1.0} |
| F5 Primary outcome | Declined ECE at severity 0, plus the frontier |
| F6 Placebo | `requested_amount`, flat world only |
| F7 Diagnostic-flag result | Descriptive table, no verdict |
| F8 Confounder strength | Every cell runs at strength 0, instead of the default |

F8 is the reason this design differs from the 2026-09-29 draft: every cell passes
`unobserved_strength=0.0`, the cell key carries the strength, and the legacy cell's
byte-identity reference is the strength-0 rows of `artifacts/surface_frontier.csv`
rather than the default-strength spaced artifact.

## 2. Mechanism (unchanged from the committed knob, `9ee84fe`)

`selection_policy: SegmentedSelection | None = None` on both generators. The cohort
is split into 5 equal-mass segments by the rank of one observed feature (stable
sort). Each segment is funded at its own rate using the generator's existing
severity-blended score inside the segment. `knockout_rates(depth, 0.6)` funds
segment 0 at `0.6 × (1 − depth)` and shares the freed volume equally among the other
four, so the overall approval rate stays 0.6 at every depth. The policy consumes no
randomness: features, planted defaults and the selection score are byte-identical
with or without a policy; only the funding mask moves. `None` is byte-identical to
the pre-knob path.

Known property, recorded: the within-segment cutoff is a quantile with an inclusive
comparison, the same convention as the global cutoff. On tied scores it can fund a
segment a few rows above its rate. The score is a continuous float and no committed
run has produced a tie. The convention is shared on purpose; changing one side alone
would break the byte-identity between the legacy cell and the frozen artifacts.

## 3. Pre-registered hypotheses

Per seed, world `w`, policy cell `p`, every cell at strength 0:

- `E_w(p)` = declined ECE of the loop's control lever (IPW reweight) at severity 0.0,
  which is round 0 and exists for every run. At severity 0 selection is random
  inside each segment, so nothing is hidden and the policy's structure is the only
  selection effect.
- `F_w(p)` = the loop's frontier severity. A run that never passed severity 0 is
  encoded as −0.2, one grid step below the minimum, and counted.
- `d0`, `d1` = the primary attack feature at depth 0 and depth 1; `legacy` = no
  policy.

Confirmatory family, m = 4, Holm α = 0.05, one-sided exact sign test AND one-sided
Wilcoxon on the 25 paired differences; both must clear, plus the floor:

- **H-C1f / H-C1s** (losing overlap costs calibration where nothing is hidden):
  `E_w(d1) − E_w(d0) > 0`. Floor: median paired difference ≥
  median |`E_w(d0) − E_w(legacy)`|, the re-cut noise scale measured inside the same
  experiment.
- **H-C2f / H-C2s** (losing overlap moves the wall): `F_w(d0) − F_w(d1) > 0`.
  Floor: median paired difference ≥ one severity step (0.2).

Placebo control, flat world, outside the family, unadjusted: the H-C1 contrast on
`requested_amount`, which has no risk coefficient and an independent draw in the
flat world. Expected not to move. "Moved" = both tests at α = 0.05 and the floor.
If it moves, H-C1f cannot be attributed to losing overlap in a risk-relevant
direction, and the docs say so.

**Falsification statement.** The overlap-wall explanation is stated as measured
only if H-C2f and H-C2s are both confirmed. If H-C1 holds and H-C2 does not, the
docs say: losing overlap costs calibration and does not produce the wall. Any
failure is reported as measured.

Descriptive, no verdicts: the vintage dose-response; the frontier distribution and
median `E` per cell; the flag × outcome table per cell over every walked round.

## 4. Sweep — `scripts/run_segment_sweep.py`

| Cells | Worlds | Count |
|---|---|---|
| legacy (policy `None`) | flat, scm | 2 |
| utilization (high) × {0.0, 0.5, 1.0} | flat, scm | 6 |
| vintage (low) × {0.0, 0.5, 1.0} | flat, scm | 6 |
| requested amount (high) × {0.0, 1.0} | flat | 2 |

16 cells × 25 seeds `{1000 + 16i, i = 0..24}` × strength 0 = **400 loop runs**,
written to `artifacts/segment_frontier.csv` with an `unobserved_strength` column.
One subprocess per run, sequential, resumable on `(policy_id, world, seed)`.
`improve_mode="both"`, exploration 0: the published loop configuration.

The seeds are the spaced set, which the v4 surface has already consumed at strength
0 for the legacy configuration. That reuse is the design: the legacy cell must
reproduce the surface's strength-0 rows byte for byte (I-C1), which fixes the seeds.
The policy cells on these seeds have never run under this design. The seeds are not
"fresh" in the replication sense, and this document does not claim they are.

## 5. Analysis — `scripts/segment_stats.py`

Recomputes everything from `segment_frontier.csv`; writes
`artifacts/segment_stats.csv`. Fail-closed: exits non-zero if any of the 400 cells is
missing or if I-C1 fails. Statistics primitives are the v3/v4 implementations in
`scripts/feedback_sweep_stats.py`.

## 6. Integrity gates

- **I-C1, publication-blocking.** The legacy cells' rows must be string-equal, on
  `unobserved_strength` and every frontier column, to the strength-0 rows of
  `artifacts/surface_frontier.csv`, per (world, seed), in iteration order. Absent
  reference cells fail closed.
- **Pilot gate before the matrix** (seed 1000, in the confirmatory set): I-C1 in
  miniature; isolation (a knockout leaves features and planted defaults
  byte-identical); non-vacuity (the mask moves, the knocked-out segment has zero
  funded rows, round-0 control metrics differ between depth 0 and depth 1); a 60 s
  per-run budget trip-wire; environment drift against `surface_env.json` reported.
- **No matrix without a published digest and an explicit go.** The digest of this
  file goes into `PREREGISTRATION.md` in a pushed commit before the matrix starts.

## 7. Disclosures: what was seen before this freeze

1. **Feasibility spike, 2026-09-29, seed 42 (outside the confirmatory set), default
   strength.** One seed. Frontiers 0.2–0.4 across cells; the flag fired on every
   knockout round including the placebo while the loop passed; a depth-0 re-cut
   moved one frontier by a grid step. This shaped the design (continuous primary
   outcome, re-cut floor, placebo), not the hypotheses' direction, which comes from
   the overlap candidate as stated in the essay draft.
2. **Pilot gate, 2026-09-29, seed 1000, default strength**, on the committed driver
   at `78a6199`: passed; round counts seen, no metric values read.
3. **Pilot gate, 2026-11-03T13:39:29Z to 13:40:32Z, seed 1000, strength 0**, on the
   revised driver: PASS. Environment matches `artifacts/surface_env.json`. Six loop
   runs (legacy, utilization d0, utilization d1 × both worlds), four rounds each, 8 s
   flat and 12 s SCM per run. Byte-match, isolation, non-vacuity and budget all
   hold. Round counts and timings were read; the pilot's metric values in
   `artifacts/segment_pilot/pilot_segment.csv` were not inspected.
4. Nothing on any other confirmatory seed under any policy cell.

## 8. Verification before any doc changes

1. Full suite green under pins; frozen baselines untouched.
2. Pilot output recorded (section 7, item 3).
3. 400 of 400 runs present; I-C1 green; `segment_stats.py` exit 0.
4. Verdicts recomputed from the raw CSV by an independent skeptic before any
   document is edited.
5. Doc-number gate with the new claims registered; manifest re-pinned for the two
   new artifacts; sphinx `-W` clean.

## 9. Out of scope

Category-native segments; a counterfactual leg (F2); multi-feature policies; the
reveal-`u` ablation (its own design); 0.4.0 release mechanics; any change to the
calibration target, the ECE binning, the model family, the severity walk, or any
committed artifact.
