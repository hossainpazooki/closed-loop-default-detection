# Handoff — v4 entry: Option A, the `unobserved_strength` × severity frontier surface

*2026-07-22 (second brief this date; supersedes nothing — the same-day
[v0.3.0 release brief](2026-07-22-v0.3.0-released.md) records the release).
Newest commit described: **`3be6c06`** (`docs: 0.3.0 release handoff and
learnings`). Measure drift from here. This brief exists to hand a v4 session
its starting ground; **no v4 artifact exists yet — everything v4 below is
planned, nothing is built.***

## Current state

- **[released]** 0.3.0 live on PyPI, effect-verified from a clean venv
  (discriminating v3-flags probe; `author_email: None`). All release gates
  green at `1ab178b`/tag `v0.3.0`; details and evidence in the same-day
  release brief.
  *re-verify:* `curl -s https://pypi.org/pypi/closed-loop-default-detection/json | python -c "import json,sys;print(json.load(sys.stdin)['info']['version'])"` (expect `0.3.0`)
- **[verified]** Working tree clean, zero untracked lines; `docs/superpowers/plans/`
  is locally excluded by operator policy (see
  `docs/learnings/2026-07-22-superpowers-plans-are-locally-excluded-by-policy.md`)
  — do not re-flag it, do not un-commit the specs.
  *re-verify:* `git status --short | wc -l` (expect `0`)
- **[verified]** Suite 203 under pins; sphinx `-W` clean; CI 15/15 on
  `ec92b43` and the release commits, vacuity-checked (skip count 9).
  *re-verify:* `.venv/Scripts/python.exe -m pytest -q`
- **[planned — nothing built]** v4 = spec §9 **Option A**: the
  `unobserved_strength` × severity **frontier surface**. No spec, no plan, no
  code, no artifact exists for it. The first v4 deliverable is a brainstormed,
  committed spec — see Open / next.

## What Option A actually is (so the v4 session doesn't reconstruct it)

- **The knob:** `unobserved_strength` scales the unobserved confounder `u` in
  *both* generators — flat: `synthetic.py:83` (default **0.7**, applied at
  `:220`); SCM: `scm.py:280` (default **0.55**, applied at `:707`/`:725` to
  selection and outcome). It is the single parameter that controls how much
  selection and default share an unobservable cause — the mechanism the whole
  assessment's failure story rests on.
- **The gap it closes:** every published frontier claim (v1 headline, v2
  Finding 1) was measured along the **severity axis only, at the fixed default
  strengths**. The honest v2 claim "operating frontier 0.2–0.4 depending on
  the draw" (assessment II.3, `artifacts/frontier_sweep.csv`) has the
  confounder axis implicit. Option A sweeps the 2-D grid and maps the frontier
  as a **surface**: how does the IPW/g-computation operating frontier move as
  the confounder strengthens or weakens?
- **Provenance nuance, stated precisely:** the phrase "cheapest most-valuable
  move" that prior briefs attach to the assessment appears in the **v3 spec
  §9** (`docs/superpowers/specs/2026-07-14-cldd-v3-design.md:311`), which
  attributes it to the assessment; `docs/assessment.md` itself does not
  contain the phrase (grep-verified this session). The assessment's actual
  staked basis for A is Finding 1 — the frontier is a distribution — plus the
  one-cause mechanism story (Part I: "one cause, measured two independent
  ways"). Cite the spec for the phrase, the assessment for the substance.
- **Deferred-not-dismissed status:** operator chose B over A for v3 (spec
  decision record 1 — locked, and now discharged by the 0.3.0 release);
  §9 names A "a natural v4 alongside C". Option C (structured/segmented
  selection) remains deferred and is *not* part of this entry's scope unless
  the operator says so.

## Locked decisions (inherited into v4 — pick-up checks premises, doesn't relitigate)

- **Passive pricing; EMP is reporting-only, never a gate; EMPC never in a
  hypothesis or headline** (v3 spec decision 2/3; assessment II.7). Reason:
  an endogenous cutoff would confound the selection mechanism under study.
- **Every headline carries "verified experiment, not verified result"** —
  planted, risk-unlinked timing (v2 §2 label; assessment II.7). A frontier
  surface inherits this label wholesale.
- **Byte-identity of default paths is the compatibility contract.** Any v4
  knob must be additive with byte-exact defaults, enforced **differentially**
  (the `_load_pre_v3_feedback` pattern), never via a stored constant. Note:
  `unobserved_strength` is *already a constructor parameter* in both
  generators, so a sweep may not even need new flags — check before adding any.
- **Sweep-first discipline:** results are written only after the full matrix
  runs; docs carry distributions, never a single seed (v3 spec §8 pattern).
- **Spaced seed sets for multi-generation runs** (v3: {1000+16i}; inherited
  overlapping seeds were rejected because 12-gen runs consume s..s+11).
  Whether Option A's runs are multi-generation is a spec decision — but if
  they are, the spacing rule applies unamended.
- **Pilot gate before any full matrix** (v3 spec §10.3; the dq-fail-closed
  pattern that caught two real defects at the v3 firing). A 2-D grid
  multiplies runtime — v3's 1-D matrix was already 450 runs — so the pilot
  gate and a runtime budget are non-negotiable spec items, not options.
- **Repo process pattern:** brainstorm adversarially → **committed spec**
  (pre-registered hypotheses, gates, amendments by revision) → **local plan**
  (gitignored per policy) → build → gates. The spec is the scientific
  contract; v3's Rev 2.1/2.2 show amendments happen by revision, never by
  loosening a tolerance.
- **Registered defects stay registered** (`TARGET_DECLINED_ECE = 0.10`, ECE
  binning, model family — v3 spec §9). Out of scope again unless the v4 spec
  explicitly re-opens one *as a spec decision*.

## Reuse map

- `scripts/run_frontier_sweep.py` → `artifacts/frontier_sweep.csv` — the
  existing 25-seed × both-worlds **severity** sweep; Option A's closest
  ancestor. Read it before designing the grid: the surface sweep is plausibly
  this plus one axis.
- `scripts/run_feedback_sweep.py` — the v3 shard-per-run, subprocess-per-run
  driver with `--quick` pilot; the scaling pattern for any big matrix.
- `scripts/feedback_sweep_stats.py` + `cldd/feedback_stats.py` — the
  stats-module-behind-thin-CLI pattern: recomputes every published number
  from the committed artifact, exits non-zero when a gate fails (publication
  mechanically blocked). Clone this shape for surface stats.
- `unobserved_strength` plumbing already exists end-to-end in both generators
  (`synthetic.py`, `scm.py`) — no generator surgery expected.
- Identity machinery (`tests/test_feedback_flags.py`: `_load_pre_v3_feedback`,
  module-scoped fixtures, `_serialize_v1_fields`) — reuse if any default path
  is touched; never store a new constant.
- `scripts/paired_significance.py`, Holm + prior-arm-MAD floor pattern
  (v3 spec §5) — the hypothesis-testing template if v4 pre-registers tests.
- Docs slots unchanged: `how-it-works.md` / `validation.md` /
  `configuration.md`; long-form never returns to the README.

## Invariants

Unchanged from the release brief; the ones a v4 builder would most plausibly
break, restated:

- Never modify `artifacts/*.csv` or frozen baselines; new artifacts are new
  files. Byte-determinism per seed; randomness only via seeded
  `numpy.random.Generator` streams seeded from `ctx`.
- No unmarked float-exact-against-a-constant test — differential or `pinned`.
- `fetch-depth: 0` stays on every pytest CI job; skip count 9 is right, 12
  means the identity gate went vacuous.
- Gates: `pytest` (203 under pins), coverage, `sphinx -b html -W` (0 warnings,
  no mermaid in `docs/*.md`, new `docs/` subdirs Sphinx-excluded), wheel ships
  `py.typed`. `_check_sample_weight` watch on sklearn major bumps.
- ASCII-only `print()` in scripts (Windows cp1252 console).

## Open / next

1. **First action: adversarial brainstorm → v4 spec** for Option A, committed
   under `docs/superpowers/specs/` (the scientific contract; plans stay
   local). The spec must decide, at minimum: the grid (which
   `unobserved_strength` values × which severities — the defaults 0.7/0.55
   should be grid points so existing results embed in the surface), worlds
   (flat, SCM, or both — Finding 1 measured both), per-cell protocol (loop
   frontier vs single-generation, seeds, spacing), the pre-registered claim
   shape (what does "the frontier moves with confounder strength" predict,
   falsifiably?), runtime budget + pilot gate, and the artifact/stats-gate
   pair. Scope decisions are the **operator's** (v3 precedent: decision
   record 1).
2. **No blocker.** Tree clean, gates green, 0.3.0 closed. Version target
   would be 0.4.0 (additive), but that's a spec decision.
3. **Still open, optional:** local Linux loop (Docker Desktop / WSL
   `python3.12-venv`) — unchanged since 07-20; a 2-D sweep makes a local
   Linux check cheaper than another push-cycle CI surprise.
4. **Option C** remains deferred-not-dismissed; out of this entry's scope.
