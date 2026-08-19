# Handoff — Task 7 landed: one-cause claim withdrawn, verdicts registered, I-1 fail-closed

*2026-08-18, second entry this date (the [first](2026-08-18-v4-execution-gates-and-verdicts.md)
covered the matrix execution through Task 6). Written on `90cf40d` (pushed, CI
green) + this phase's UNCOMMITTED changes — the two-commit block was output to
the operator; pick-up measures drift from `90cf40d` and expects either those two
commits on top or the working tree carrying exactly: `README.md`, `CHANGELOG.md`,
`docs/{validation,configuration,how-it-works}.md`, `scripts/{check_doc_numbers,
surface_stats}.py`, `tests/test_surface_stats.py`, plus this brief and the two
new learnings entries.*

> **Essay-A drafting sessions:** this brief is safe except where marked; the
> verdict content lives in the README v4 section and the first brief's tail,
> both on the do-not-read list in `~/dev/briefs/2026-08-18-essay-a-outline.md`.

## Current state

- **[verified] v4 shipped through Task 6 and public.** Three close-out commits
  landed as specified (`9a2bd89` artifacts, `c6a70c1` Rev 1.2 + learnings,
  `90cf40d` changelog + brief); CI green on `90cf40d`; all six surface
  artifacts git-tracked — clone-reproducible for the first time.
  re-verify: `gh run list --limit 3 --json conclusion,headSha` ·
  `git ls-files artifacts/ | grep surface`
- **[built, uncommitted] Spec §3's falsification statement is now honored in
  the docs.** README: the "one cause explains both" sentence is withdrawn as
  measured (two qualified passages + a new registered section "The cause,
  tested by intervention (v4)" quoting five figures); long-form v4 section in
  `docs/how-it-works.md`; "The v4 surface gates" section in
  `docs/validation.md`; two knob rows in `docs/configuration.md`;
  `docs/assessment.md` untouched (dated snapshot, per repo rule).
  re-verify: `python scripts/check_doc_numbers.py` → 10 claims PASS, incl.
  `surface-verdicts`
- **[built, uncommitted] `surface-verdicts` doc-number claim.** Recomputes the
  corner count, strength-median profile, H-S1f sign test (exact binomial, Holm
  ×4), and gap-direction medians from `surface_frontier.csv` +
  `surface_counterfactual.csv` (both added to `ARTIFACTS_READ`, tracked-guard
  covered) — and asserts all four confirmatory floor checks still fail before
  emitting the "not confirmed" literal, so the gate goes red if future data
  un-falsifies a hypothesis rather than letting the README carry a stale
  falsification.
  re-verify: `python -m pytest tests/test_doc_numbers.py -q` → 6 pass
- **[built, uncommitted] I-1 frontier leg fails closed on absent cells.**
  Failing test written and observed failing first; one-line guard in
  `i1_check_frontier`; regression test pins both legs; live gate re-run still
  exits 0. Discharges the 2026-08-18 silent-pass learning's "filed for the
  next build session" same-day.
  re-verify: `python -m pytest tests/test_surface_stats.py -q` → 7 pass ·
  `python scripts/surface_stats.py` → I-1 PASS, exit 0
- **[verified] Every spec §9 gate is now discharged.** 1: suite 221 passed /
  9 skipped / 230 collected, exit 0 (Task-7 run). 2–4, 6: per the first
  2026-08-18 brief. 5: doc-number 10/10 PASS + sphinx `-W` clean, exit 0
  captured directly (the venv had silently lost the `[docs]` extra since the
  2026-08-04 rebuild — reinstalled, pins verified unchanged 1.9.0/2.4.6; see
  today's learnings entry).
  re-verify: `python -m pytest -q` (≈15 min) ·
  `python -m sphinx -b html -W --keep-going docs docs/_build/html`
- **[verified] Essay program state** (briefs side, dev-root repo): Essay A
  outline at `~/dev/briefs/2026-08-18-essay-a-outline.md` with the partition
  rule extended to the repo's new public verdict passages; evidence pack
  complete with skeptic 5a CONFIRMED; Essay B's gate-6 record complete in the
  CLASS-H file. Both essays unblocked once the pending cldd commits land.
- **[pending operator] The two-commit block + push**, then CI green — that run
  is the first CI execution of `surface-verdicts`. Until it lands, the
  qualification exists only on this machine.

## Locked decisions

- **Figures and their registration ride the same commit** (2026-07-29 lock,
  honored again here): the README v4 section and its claim function are
  inseparable in commit 2. Reason: an unregistered figure is ungated by
  construction.
- **The "not confirmed" literal is conditional on live floor re-derivation**
  (new): the claim function asserts the falsification still holds at gate
  time. Reason: a corrections-driven repo must not be able to quote its own
  falsification after the data stops supporting it.
- **The essay partition now includes the repo's public verdict passages**
  (extends the 08-18 evidence-partition lock): README v4 section,
  `how-it-works.md` v4 section, and both 08-18 briefs' marked tails are on
  Essay A's do-not-read list. Reason: spec §3 forces the repo to carry the
  verdicts; the essay embargo survives by scoping reads, not by keeping the
  repo silent.
- **`docs/assessment.md` stays untouched by v4** (standing repo rule +
  spec §8): any v4 review is a future Part IV, never a retro-fit.

## Reuse map

- `scripts/check_doc_numbers.py::claim_surface_verdicts` — pattern for a
  claim that re-derives a *verdict condition* (not just a figure) before
  emitting its literal; copy it for any future falsification-dependent text.
- `tests/test_surface_stats.py::test_i1_frontier_fails_closed_on_absent_cell`
  — toy-CSV pattern for pinning a comparator's empty-input behavior.
- `~/dev/briefs/2026-08-18-essay-a-i1-evidence.md` — Essay A's complete
  casualty-2 evidence; `…-essay-b-confirmatory-verdicts-CLASS-H.md` — Essay
  B's verdict record with doc-language guidance (§4).
- `docs/superpowers/plans/2026-08-18-cldd-v4-execution-a-pivot.md` — executed
  plan whose end-of-file log records every deviation; read it before trusting
  any claim about how this day went.

## Invariants

- The doc-number gate is now **10 claims**; any README edit near a registered
  literal must keep the gate green (`python scripts/check_doc_numbers.py`).
- I-1 is fail-closed on **both** legs now — do not "simplify" the
  `if not want` guard away; the regression test exists to stop that.
- `artifacts/*.csv` frozen baselines, the 07-29 spaced originals, and the
  v4env reference pair are immutable; ledger entries are immutable
  (supersede with `kills:`, never edit).
- Class-G/H partition per the execution plan's Global Constraints — violating
  it invalidates Essay A's central honesty claim.

## Open / next

1. **Operator: run the two commits + push; confirm CI green** (first
   `surface-verdicts` run in CI). Then, optionally, the dev-root commits for
   the essay-side briefs.
2. **Essay A drafting session** (briefs side): invoke writing-plans against
   `~/dev/briefs/2026-08-18-essay-a-outline.md`. All publication-checklist
   inputs are satisfied except the CI confirmation in (1).
3. **Essay B drafting** follows A (publication order locked in the design).
4. **Later, unblocked**: 0.4.0 release mechanics (CHANGELOG `[Unreleased]` →
   dated at release, per spec §8); a future assessment Part IV if wanted.
