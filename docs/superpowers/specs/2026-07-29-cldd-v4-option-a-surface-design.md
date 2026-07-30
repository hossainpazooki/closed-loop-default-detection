# CLDD v4 — Option A: the `unobserved_strength` × severity frontier surface

*Spec written 2026-07-29 (brainstormed with the operator; scope decisions are the
operator's, recorded below). Target version: **0.4.0** (additive). Entry ground:
`docs/handoff/2026-07-22-v4-entry-option-a.md`. Process per the repo contract:
committed spec → local plan (gitignored) → build → gates; amendments by revision,
never by loosening a tolerance.*

## 0. Purpose — why v4 exists

**v4 turns the repo's central mechanism claim from a coincidence into an
intervention.**

Every headline CLDD result rests on one causal story: the loop's two failure
modes are *the same wall measured two ways*. The IPW frontier breaks at
severity ~0.4–0.6, and the g-computation advantage collapses across the same
boundary — both, allegedly, because selection flows through the unobserved
confounder `u`. As assessment Part III critique 2 concedes, the current
evidence for "same wall" is **location-coincidence**: with four severities, two
independent failure modes landing on the same grid step is not rare — and
everything was measured at one arbitrary confounder strength, the defaults the
generators happened to ship with (flat 0.7, SCM 0.55), which nobody has ever
defended.

Because the harness owns the world, `unobserved_strength` is directly
manipulable. Option A sweeps it as an axis and makes the mechanism claim
falsifiable:

- **If the story is right**: turn the cause down and both walls must recede
  *together*; at strength 0 both must vanish (nothing unobservable remains, so
  IPW and g-computation should hold at every severity). Turn it up past the
  defaults and both must advance together.
- **If the walls don't move together** — the frontier stays put while the
  gap-collapse moves, or either wall survives at strength 0 — the one-cause
  narrative that anchors the published essay and assessment is wrong, and that
  is a finding to publish, not bury.

Secondary payoffs: the published frontier gets an error bar on the axis it was
silently conditioned on (the same spirit as the 2026-07-29 spaced-seed rerun,
which already showed the SCM frontier median is draw-dependent); Part III's
reveal-`u` ablation is absorbed as the strength-0 corner (the *world-side*
variant — see §10 for the banked estimator-side variant); and the practitioner
reading of the surface is the actionable question a real lender would ask —
*how strong does unobserved confounding have to be before correction stops
being trustworthy?*

## Decision record (forks closed during brainstorming, 2026-07-29)

1. **Scope: both surfaces** (operator choice). The frontier surface (loop) AND
   the counterfactual-gap surface (g-computation) are swept across the same
   strength grid. Rationale: the one-cause claim is only falsifiable if both
   walls are measured; the frontier-only variant was rejected as leaving the
   mechanism claim untested.
2. **Strength grid: 6 points, {0.0, 0.2, 0.4, 0.55, 0.7, 1.0}** (operator
   choice). Both shipped defaults are embed points (existing published results
   lie on the surface); 0.0 anchors the no-confounding corner; 1.0 is the
   above-default extrapolation point.
3. **Counterfactual severity protocol: hybrid** (operator choice). Full
   severity curve {0.4, 0.6, 0.8, 1.0} at the three anchor strengths
   {0.0, 0.55, 1.0}; endpoints {0.4, 1.0} at {0.2, 0.4, 0.7}. Locates the
   gcomp wall where the location claim needs it; embeds the published
   severity-collapse curve at the SCM default.
4. **Counterfactual leg is SCM-only.** `run_counterfactual_eval` and its
   queries are SCM-native; the published counterfactual claims are SCM-based.
   The flat world appears only in the frontier leg (both worlds, all six
   strengths).
5. **Seeds: the spaced set {1000 + 16i, i = 0..24}, both legs.** Spacing 16
   exceeds every within-run consumption span (loop: ≤6 measure seeds + train
   block at offset 1000; counterfactual: `{s, s+1000}`), so runs within a
   (world, strength) or (strength, severity) cell are seed-disjoint; the same
   seed across cells is deliberately paired, as in the 2026-07-29 replication.
   Bonus: the default-strength cells at these seeds are *exactly* the
   2026-07-29 spaced-sweep runs, which yields a free byte-identity integrity
   gate (§7, I-1).
6. **Inherited locks honored unchanged**: passive pricing / EMP never a gate /
   EMPC never in a hypothesis; "verified experiment, not verified result"
   label on every headline; additive knobs with byte-exact defaults; sweep
   -first (no doc numbers before the full matrix); pilot gate before any
   matrix; registered defects stay registered; artifacts immutable — new
   files only.

## 1. Core module changes (the only two, both additive)

- **`SelectiveLabelsLoop(generator_kwargs: dict | None = None)`** — threaded
  through `_new_generator` → `make_generator(generator, ..., **(generator_kwargs
  or {}))`. `None` (default) is byte-identical to today's path. The surface
  driver passes `{"unobserved_strength": v}`.
- **`run_counterfactual_eval(..., unobserved_strength: float | None = None)`**
  — forwarded to the internal `StructuralBorrowerGenerator(...)` construction
  only when `generator is None` and the value is not `None`. Default
  byte-identical. (Chosen over external generator construction so the driver
  cannot drift from the eval's own construction defaults.)

No other src change. `make_generator` gains `**extra` forwarding; the SCM
path's `independent_selection_noise=True` behavior is untouched.

## 2. What is NOT changing

The severity walk (`START_SEVERITY`/`SEVERITY_STEP`/`MAX_SEVERITY`/
`MAX_ROUNDS`), `TARGET_DECLINED_ECE = 0.10` and its binning (registered
defects), the estimator feature sets (no reveal-`u` — banked, §10), correctors,
EMP layer, feedback module, all committed artifacts and baselines.

## 3. Pre-registered hypotheses

Notation: `F_w(v)` = per-seed loop `frontier_severity` in world `w` at strength
`v`; `g(v, sev)` = per-seed strong-propagation gap (`naive_strong −
gcomp_strong`) at strength `v`, severity `sev` (SCM); `Δ(v) = g(v, 0.4) −
g(v, 1.0)` (the per-seed collapse). Defaults: `d_flat = 0.7`, `d_scm = 0.55`.

**Confirmatory family (Holm-corrected, m = 4, α = 0.05; each tested by
one-sided exact sign test AND one-sided Wilcoxon on the 25 per-seed paired
differences — both must clear, plus the effect floor):**

- **H-S1f** (flat frontier wall is cause-driven): `F_flat(0.0) − F_flat(0.7) >
  0` per seed. Floor: median paired difference ≥ one severity step (0.2) —
  the frontier is grid-quantized, so anything smaller is not a move.
- **H-S1s** (SCM frontier wall is cause-driven): `F_scm(0.0) − F_scm(0.55) >
  0` per seed. Same floor.
- **H-S2a** (counterfactual gap is cause-driven): `g(0.55, 0.4) − g(0.0, 0.4)
  > 0` per seed. Floor: median paired difference ≥ median |g(0.0, 0.4)| across
  seeds — the strength-0 gap *is* the estimator-noise scale, measured inside
  the same experiment.
- **H-S2b** (the collapse is cause-driven): `Δ(0.55) − Δ(0.0) > 0` per seed.
  Floor: median paired difference ≥ median |Δ(0.0)|.

**Corner prediction (recorded, informal):** at strength 0.0 the loop should
pass every severity it walks (frontier = the grid maximum) for a majority of
seeds in both worlds, and `g(0.0, ·) ≈ 0` at every severity. Reported
descriptively; the confirmatory content lives in H-S1/H-S2.

**Falsification statement:** the "one wall / one cause" narrative survives
into any doc only if **all four** confirmatory hypotheses pass. Any failure is
reported as measured (v3's H2 precedent), and the mechanism language in
README/docs gets qualified in the same change — no softening, no burial.

**Secondary / descriptive (no verdicts, no Holm):** the full 6-point surface
per world (median/min/max frontier per strength; gap curves per anchor
strength); monotonicity read-off (median `F_w(v)` non-increasing in `v`;
median `g(v, 0.4)` non-decreasing in `v`); wall-location movement from the
anchor-strength severity curves; the strength-1.0 extrapolation cells; the
cross-default cells (flat @ 0.55, SCM @ 0.7).

## 4. Sweep — `scripts/run_surface_sweep.py`

- **Frontier leg:** 6 strengths × {flat, scm} × 25 spaced seeds = **300 loop
  runs** (`improve_mode="both"`, exploration 0 — the published loop
  configuration), one JSON line per round, appended to
  `artifacts/surface_frontier.csv` (schema = `frontier_sweep.csv` fields +
  leading `unobserved_strength`).
- **Counterfactual leg (SCM only):** anchors {0.0, 0.55, 1.0} × severities
  {0.4, 0.6, 0.8, 1.0} × 25 seeds = 300 evals; {0.2, 0.4, 0.7} × {0.4, 1.0} ×
  25 = 150 evals; **450 evals total**, appended to
  `artifacts/surface_counterfactual.csv` (schema = `seed_sweep_25.csv` fields
  + leading `unobserved_strength`).
- Same discipline as every prior driver: ONE SUBPROCESS PER RUN, strictly
  sequential, resumable append keyed on (strength, world/severity, seed),
  ASCII stdout.
- **Runtime budget:** ~27.5 h total on this machine (measured 2026-07-29:
  loop ≈ 2.5 min, eval ≈ 2 min). Resumable across ≥2 overnight tranches.
  **Budget trip-wire:** if the pilot's per-run times exceed 2× these
  estimates, STOP and re-scope by spec revision — do not silently shrink the
  grid.
- `.gitignore`: the two new artifact CSVs (plus the stats CSV, §5) get
  explicit `!artifacts/...` exceptions **in the same commit that adds the
  driver** — `artifacts/*` is default-deny, and an unexcepted artifact makes
  the doc-number gate fail closed on any fresh clone (2026-07-29 lesson).

## 5. Analysis — `scripts/surface_stats.py`

Recomputes every to-be-published number from the two committed artifact CSVs
(never from memory): per-cell distributions, the four confirmatory tests with
Holm and floors, the corner-prediction summary, the descriptive surface.
Writes `artifacts/surface_stats.csv` (flat one-row-per-statistic schema, v3
`feedback_sweep_stats.csv` pattern: descriptive values rounded 4dp, p-values
full precision). **Exits non-zero** — publication mechanically blocked — if
any confirmatory computation is unevaluable (missing cells = fail-closed) or
any §7 integrity control fails.

## 6. Artifacts invariant

`frontier_sweep.csv`, `frontier_sweep_spaced.csv`, `seed_sweep_25.csv`,
`seed_sweep_spaced.csv` and every other committed artifact are untouched. The
surface writes only the three new files named above.

## 7. Determinism, integrity, and testing

- **I-1 (byte-identity embed gate, publication-blocking):** the surface's
  default-strength cells re-run the *exact* 2026-07-29 spaced-sweep
  configurations, so: `surface_frontier.csv` rows at (flat, 0.7) and
  (scm, 0.55) must be **string-equal field-for-field on every shared column**
  with the corresponding `frontier_sweep_spaced.csv` rows (the new
  `unobserved_strength` column is the only permitted difference), and
  `surface_counterfactual.csv` rows at (0.55, {0.4, 1.0}) likewise against
  `seed_sweep_spaced.csv`. Any mismatch is a driver-plumbing bug;
  `surface_stats.py` enforces this and exits non-zero.
- **Pilot gate (before the matrix, ~15 min):** `run_surface_sweep.py --pilot`
  = seed 1000 only × {flat@0.7, scm@0.55, scm@0.0} loop runs + cf evals at
  (0.55, 0.4) and (0.0, 0.4). Asserts: (a) the overlap rows byte-match the
  spaced artifacts (I-1 in miniature); (b) **non-vacuity** — the strength-0.0
  cohort differs from the default cohort (the knob demonstrably reaches the
  world), and its round-0 metrics differ. Fails mechanically before ~27 h are
  spent.
- **New unit tests:** default-vs-explicit-default byte-equality for both new
  knobs (in-process differential, no stored constants, NOT `pinned`);
  `generator_kwargs=None` path unchanged (existing frozen-baseline and
  identity tests already cover it — they must stay green untouched);
  `run_counterfactual_eval(unobserved_strength=0.0)` produces a cohort whose
  `u` does not enter selection/outcome (assert via the generator's own state,
  not via downstream floats).
- All existing gates hold: suite green under pins, `fetch-depth: 0` / skip
  count 9, sphinx `-W`, wheel ships `py.typed`, ASCII stdout.

## 8. Documentation

Sweep-first: no README/docs number until the matrix completes and
`surface_stats.py` exits 0. Then: a short README v4 block (both-designs
convention as with the spaced rerun), long-form in `docs/how-it-works.md`,
gate row in `docs/validation.md`, knob rows in `docs/configuration.md`.
**Every quoted figure is registered in `scripts/check_doc_numbers.py` in the
same change** (2026-07-29 lock). `docs/assessment.md` untouched — any v4
review is a future Part IV. CHANGELOG under `[Unreleased]` → dated at the
0.4.0 release.

## 9. Verification gates before merge

1. Full suite green under pins, including the new knob-identity tests, with
   zero changes to existing frozen baselines.
2. Pilot gate passed BEFORE the matrix launched (record its output).
3. 300/300 loop runs + 450/450 evals present (driver reports zero missing
   keys).
4. I-1 byte-identity gate green; `surface_stats.py` exit 0.
5. Doc-number gate PASS with the new claims registered; sphinx `-W` clean.
6. Independent skeptic pass on the confirmatory verdicts before any doc
   update (refute-before-publish, per repo rigor rules).

## 10. Out of scope (named, deliberate)

- **Reveal-`u` as an observed feature** (the estimator-side ablation at
  default strength, with an irrelevant-noise negative control) — banked. It
  is the sharpest mechanism test but needs estimator feature-set plumbing
  under the byte-identity contract; the strength-0.0 corner covers the
  world-side variant. Revisit after the surface is read.
- Option C (structured/segmented selection) — deferred, untouched.
- Flat-world counterfactual leg (no SCM queries there).
- Any EMPC-based hypothesis; any change to registered defects
  (`TARGET_DECLINED_ECE`, binning, model family).
- Label accumulation; feedback-module changes; release mechanics (0.4.0
  release is its own later step).
