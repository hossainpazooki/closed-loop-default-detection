# Handoff — Part III path (b): spaced-seed rerun done, doc-number gate live

*2026-07-29. Written with the working tree carrying this session's uncommitted
changes on top of **`0bc6cd8`** (the 07-24 brief's commit, run by the operator
mid-session; this session's own commits were output as commands). Continues
the chain:
[v0.3.0 release](2026-07-22-v0.3.0-released.md) →
[v4 entry](2026-07-22-v4-entry-option-a.md) →
[essay + Part III](2026-07-24-essay-published-and-part-iii.md) → this.*

## Current state

- **[built + verified] Spaced-seed rerun (assessment III.2-1).**
  `scripts/run_spaced_sweeps.py` re-ran both sweeps on {1000+16i, i=0..24} into
  NEW artifacts (`seed_sweep_spaced.csv`, `frontier_sweep_spaced.csv`,
  `paired_significance_spaced.csv`); originals untouched. Results, all
  skeptic-recomputed from the raw CSVs:
  - Counterfactual sev 0.4: **+0.0129 ± 0.0102, 22/25 positive, Wilcoxon
    p = 1.639e-06** (t-p 7.74e-07); sev 1.0: +0.0024 ± 0.0030, 20/25,
    p = 3.75e-05. The effect survives an independent design.
  - Frontier: flat median 0.4 (18/25 at 0.4); **SCM median 0.4 (15/25 at
    0.4, 10/25 at 0.2) — the published SCM median 0.2 does NOT replicate**
    on seed-disjoint runs.
  *re-verify:* `python scripts/paired_significance.py --sweep-csv
  artifacts/seed_sweep_spaced.csv` · collapse `frontier_sweep_spaced.csv` by
  (generator, seed)
- **[built + verified] Part III critique-1 premise corrected** (adversarial
  source audit): a counterfactual run consumes only `{s, s+1000}`, so the OLD
  counterfactual set had zero cross-run collisions — the overlap caveat was
  real for the **loop sweep only** (10 colliding pairs per generator). The
  counterfactual rerun is a *replication* (p 1.5e-7 → 1.6e-6 is design
  variability), the frontier rerun a *repair*. Recorded in
  `docs/learnings/2026-07-29-seed-overlap-caveat-applied-to-only-one-sweep.md`;
  README says exactly this. Part III itself stays frozen with its
  over-generalized premise (dated doc).
  *re-verify:* `src/cldd/counterfactual.py` (~line 662: `train_rs = seed +
  config.TRAIN_SEED_OFFSET`; generator/query streams use `seed`)
- **[built + verified] Doc-number gate (assessment III.3).**
  `scripts/check_doc_numbers.py`: 9 claims, every README empirical figure
  recomputed from committed artifacts at the doc's quoted precision;
  fail-closed (unevaluable = FAIL). Wired into CI via
  `tests/test_doc_numbers.py` (5 tests, runs in every job, not `pinned`);
  planted-mismatch test proves it fires. **Maiden run caught real drift:** H4
  "≤1e-10" (true max err 1.0000000567e-10 — README now quotes the measured
  value), "149 tests" (→208), Status/citation "0.2.0" (→0.3.0).
  *re-verify:* `python scripts/check_doc_numbers.py` (expect PASS ×9) ·
  `pytest tests/test_doc_numbers.py`
- **[verified] Gates at session end:** full suite **208 passed under pins**
  (fresh run, exit 0); Sphinx `-W` clean; doc-number gate PASS ×9;
  `paired_significance.py` default path byte-identical to the committed
  artifact after its `--sweep-csv/--out-csv` extension.
  *re-verify:* `.venv/Scripts/python.exe -m pytest -q` ·
  `git diff artifacts/paired_significance.csv` (tracked, so empty = unchanged)
- **[not started]** v4 Option A spec (reveal-`u` ablation folds in there);
  Part III's remaining proposed tests (IPW clip sensitivity,
  graph-misspecification, mutation run, `k==m` fallback, property-based
  invariants); essay-URL pointer; local Linux loop.

## Locked decisions

All prior locks hold. New this session:

- **The spaced artifacts are additive, never replacements.** The overlapping
  sweeps stay committed and quoted (comparability + provenance); the README
  quotes both designs side by side. Reason: replacing them would silently
  rewrite the published evidence base.
- **README carries both p-values** (1.5e-7 committed design, 1.6e-6 spaced) —
  Part III's "quote those p-values" honored without erasing the published one.
- **New README figures must be registered in `check_doc_numbers.py`** in the
  same change. Reason: the gate's coverage is its registry; an unregistered
  figure is ungated by construction.

## Reuse map

- `scripts/run_spaced_sweeps.py` — pattern for any future spaced sweep
  (resumable append, subprocess-per-eval, within-cell seed-disjointness note).
- `scripts/check_doc_numbers.py` — add a claim function + registry row per new
  quoted figure; `sci_short`/`sci_padded`/`signed` match README conventions.
- The skeptic finding that severity does not alter stream consumption
  (`scm.py` ~957: severity is a scalar blend over pre-drawn frozen noise)
  means (s, 0.4) and (s, 1.0) are a deliberate paired design — reuse for any
  cross-severity contrast.

## Invariants

Unchanged from prior briefs (artifacts immutable, byte-determinism,
`fetch-depth: 0`, sphinx `-W`, ASCII stdout, exclude patterns anchored). Plus:
the doc-number gate is now part of the suite — a README figure edit without
its artifact recompute fails CI by design.

## Open / next

1. **Operator: run the commit commands** (output in-session; four commits +
   push — the 07-24 brief already landed as `0bc6cd8`). Note the three new
   `!artifacts/*_spaced.csv` gitignore exceptions ship with the replication
   commit: without them a fresh clone lacks the CSVs and the doc-number gate
   fails closed on CI.
2. **Choice point restated:** v4 Option A spec is now the clear next build
   (Part III's priorities are discharged: spaced rerun done, doc-number gate
   live; the reveal-`u` ablation was always v4's opening move). The SCM-median
   non-replication is one more datum for the v4 spec: the frontier's center is
   draw-dependent — design Option A's severity grid accordingly.
3. **Optional, unchanged:** essay-URL pointer; local Linux loop. The essay's
   "SCM median 0.2" sentence rests on the overlapping design — operator may
   want to annotate the published essay with the spaced result.
