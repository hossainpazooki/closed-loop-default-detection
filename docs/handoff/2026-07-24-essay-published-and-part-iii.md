# Handoff — essay published, publication remediation landed, assessment Part III

*2026-07-24. Newest commit described: **`f8c9cb2`** (`docs: assessment Part III`),
CI green on it. Measure drift from here. Continues the same-topic chain:
[v0.3.0 release](2026-07-22-v0.3.0-released.md) →
[v4 entry](2026-07-22-v4-entry-option-a.md) → this.*

## Current state

- **[published, external]** The essay ("When You Can't Measure What Matters",
  describing v0.3.0) is published by the operator. Every empirical figure in it
  was recomputed from the committed artifacts pre-publication and matched
  (assessment §III.1); the one ambiguity found (+0.0003 is the *overall*
  max-severity gap, not strong-propagation's +0.0017) was fixed pre-publication.
  **The essay's public URL is not recorded in this repo** — operator holds it;
  a README or CITATION pointer is optional future work.
  *re-verify:* `docs/assessment.md` §III.1 for what was checked and against what
- **[built + landed]** Publication remediation, all four critique items
  (`473f328`, `416e3a2`):
  1. Root `SESSION_HANDOFF.md` relocated to
     `docs/handoff/2026-06-26-session-handoff-hackathon-era.md` with a visible
     redaction header (machine paths, private-dataset location, stale "private"
     visibility line removed; every figure frozen).
  2. GitHub Release **v0.3.0 live** (published 2026-07-22T18:01Z from the
     CHANGELOG entry).
  3. README first screen: `pip install`, one-command reproduction
     (`scripts/paired_significance.py`), and the load-bearing identity sentence
     (validation harness, **not** a credit-modeling toolkit).
  4. Fidelity claim date-stamped in `docs/validation.md`: gate **re-run
     2026-07-22 against the private dataset — PASSED, 51/51 rows (36 counted +
     15 informational), exit 0**; explicitly a dated claim, not standing.
  *re-verify:* `gh release view v0.3.0 --json isDraft,publishedAt` ·
  `git ls-files SESSION_HANDOFF.md` (expect empty) · README top ·
  `grep "Last verified" docs/validation.md`
- **[built + landed]** The durable handoff **index is now actually tracked**
  (`416e3a2`). It had never been committed: the unanchored `HANDOFF.md` exclude
  pattern silently matched `docs/handoff/HANDOFF.md` across three prior
  "ledger" commits. Patterns anchored (`/HANDOFF.md`, `/CLAUDE.md`) — but
  `.git/info/exclude` is machine-local and does not travel with a clone.
  *re-verify:* `git ls-files docs/handoff/HANDOFF.md` (expect the path) — full
  record in `docs/learnings/2026-07-22-unanchored-exclude-swallowed-the-handoff-index.md`
- **[built + landed]** Assessment **Part III** (`f8c9cb2`): the pre-publication
  verification pass ([verified] — all essay figures recomputed exact, math
  spot-checks pass) plus a **ranked list of [proposed] methodology critiques
  and tests, none of which has been run**: pseudo-replicated seeds under the
  v1/v2 p-values; reveal-the-confounder ablation for the "one wall" claim; IPW
  clip-bound sensitivity (`model_pd.py:170` clips propensity to (0.05, 0.95));
  graph-misspecification sensitivity for g-computation; truth-defined
  strong-prop subset disclosure; within-seed ECE uncertainty; doc-number gate;
  systematic mutation run; `k == m` fallback test; property-based invariants.
  *re-verify:* `git show f8c9cb2 --stat` · read `docs/assessment.md` Part III
- **[verified]** CI 15/15 green through `f8c9cb2`; suite 203 under pins; 0.3.0
  on PyPI effect-verified (2026-07-22, clean venv, discriminating v3-flags
  probe).
  *re-verify:* `gh run list --limit 1 --json headSha,conclusion` ·
  `.venv/Scripts/python.exe -m pytest -q`
- **[not started]** Everything v4 (Option A) and everything in Part III's
  proposed-test list.

## Locked decisions

All prior locks hold (see the two 2026-07-22 briefs): passive pricing / EMP
never a gate; verified-experiment label; differential byte-identity, no stored
constants; sweep-first; spaced seeds for multi-generation runs; pilot gate
before any matrix; registered defects stay registered; plans local + gitignored,
specs committed; PyPI scrub forward-only; git history is the operator's. New
this session:

- **Assessment parts are append-only** — Part III was added without touching
  Parts I/II, per the document's own supersede-never-edit rule. Reason: the
  assessment is provenance; its parts are dated snapshots. Any future review is
  Part IV.
- **Redaction ≠ retro-fitting.** The relocated 2026-06-26 handoff had paths and
  a false visibility line removed under a visible header note; its figures are
  untouched. Reason: privacy/accuracy edits with a disclosure note preserve
  provenance; silent figure edits destroy it. Apply the same shape to any
  future scrub.
- **Part III items are proposed, not committed work.** Reason: the
  implemented-vs-planned boundary is the repo's core discipline; do not let the
  ranked list read as a roadmap promise in any public phrasing.

## Reuse map

- **Part III §III.2/III.3 is the menu for the next increment of rigor** — each
  item carries its test design. Priority per §III.4: spaced-seed rerun,
  reveal-`u` ablation, doc-number gate.
- The **v4 entry brief** (`2026-07-22-v4-entry-option-a.md`) is the build
  ground for Option A: knob locations, inherited locks, sweep/stats/identity
  reuse pointers. Note the convergence: Part III's reveal-`u` ablation
  (strength 0) **is a point on the Option A surface** — the v4 spec can absorb
  it as its opening hypothesis rather than running it separately.
- Everything in the release brief's reuse map still stands
  (`feedback_sweep_stats.py` pattern, identity-test machinery, docs slots).

## Invariants

Unchanged (see the v4 entry brief for the full list a builder would break):
artifacts immutable, byte-determinism, differential-or-`pinned` float tests,
`fetch-depth: 0` + skip-count 9, sphinx `-W` clean, wheel ships `py.typed`,
ASCII stdout. Plus, from this session: **anchor root-only exclude patterns
with `/`** — and remember `.git/info/exclude` is machine-local; on a fresh
clone the root `CLAUDE.md`/`HANDOFF.md` working notes are simply absent, not
excluded.

## Open / next

1. **Choice point, operator's:** (a) open the **v4 Option A spec** per the v4
   entry brief, folding in Part III's reveal-`u` ablation as its first
   hypothesis; or (b) run Part III's standalone priority tests first
   (spaced-seed rerun is the cheapest repair of the weakest published
   evidence; doc-number gate compounds forever). Path (a) subsumes the
   ablation; path (b) hardens what is already published. No blocker on either.
2. **Optional:** record the essay's public URL in the repo (README closing note
   or CITATION) once stable.
3. **Optional, still open since 07-20:** local Linux loop (Docker Desktop /
   WSL `python3.12-venv`).
