# Handoff — World-testing build landed in the tree; both specs still proposed

*2026-09-29. Written on `5f01105` (pushed, CI green) **plus an uncommitted
working tree**: 17 paths from the build, and this brief with four learnings
entries and their index rows. Pick-up measures drift from `5f01105` and from
that file list. Session: `cldd-v4-world-testing`.*

## Current state

- **[built, committed] A suffixed spaced run no longer overwrites the committed
  environment manifest.** `scripts/run_spaced_sweeps.py --out-suffix NAME`
  writes `artifacts/surface_env_NAME.json`; `write_env_manifest` has no default
  target. Three regression tests. Landed in `5f01105`.
  re-verify: `.venv/Scripts/python.exe -m pytest tests/test_spaced_manifest.py -q` → 3 pass
- **[built, uncommitted] Segmented selection policy and generator knob.**
  `src/cldd/selection.py`; `selection_policy=` on both generators; exported as
  `cldd.SegmentedSelection` and `cldd.knockout_rates`. `src/cldd/loop.py` is
  unchanged: `generator_kwargs` already forwards the knob.
  re-verify: `.venv/Scripts/python.exe -m pytest tests/test_selection.py tests/test_segment_knobs.py -q` → 25 pass
- **[built, uncommitted] Segmented-selection sweep driver and stats.**
  `scripts/run_segment_sweep.py`, `scripts/segment_stats.py`. 16 cells × 25
  seeds = 400 loop runs when launched.
  re-verify: `.venv/Scripts/python.exe -m pytest tests/test_segment_sweep.py tests/test_segment_stats.py -q` → 24 pass
- **[built, uncommitted] Strength-1.0 replication driver and stats.**
  `scripts/run_strength_replication.py`, `scripts/strength_replication_stats.py`.
  Fresh seeds `{5000 + 16i}`; 6 cells × 25 seeds = 150 loop runs when launched.
  No `src/` change.
  re-verify: `.venv/Scripts/python.exe -m pytest tests/test_strength_replication.py -q` → 18 pass
- **[built, uncommitted] Gitignore exceptions and the test count.** Four
  `!artifacts/...` lines; README and `docs/validation.md` say 316 tests.
  re-verify: `.venv/Scripts/python.exe scripts/check_doc_numbers.py` → 13 PASS, exit 0
- **[verified] The default path did not move.** Full suite under the pins:
  307 passed, 9 skipped, all nine being fidelity tests for a dataset path that
  no longer exists on this machine. No tracked file under `artifacts/` or
  `tests/` differs from `5f01105`. Docs build with warnings as errors: exit 0.
  re-verify: `.venv/Scripts/python.exe -m pytest -o addopts="" -q -rs` · `git diff --name-only 5f01105 -- artifacts tests` → empty
- **[verified] Both pilot gates pass, on spaced seed 1000 only.** Console output
  is in the Evidence section below.
  re-verify: `.venv/Scripts/python.exe scripts/run_strength_replication.py --pilot` · `.venv/Scripts/python.exe scripts/run_segment_sweep.py --pilot` (both write only under git-ignored pilot folders)
- **[not run] Neither experiment matrix.** No fresh seed has been touched.
  re-verify: `ls artifacts/strength_replication_frontier.csv artifacts/segment_frontier.csv` → both absent
- **[proposed] Both specs.** Drafts live outside the repo, in the operator's
  local briefs folder: `2026-09-29-cldd-strength-1.0-replication-spec-draft.md`
  (six open forks, R1–R6) and
  `2026-09-29-cldd-option-c-segmented-selection-spec-draft.md` (eight open
  forks, F1–F8). Neither is ratified. Nothing under `docs/superpowers/specs/`
  was added.
- **[planned] Everything after the build**: spec ratification, the matrix runs,
  analysis, the skeptic pass on verdicts, docs, claim registration, hash
  re-pins. These stay in the two parent plans (local, git-excluded):
  `docs/superpowers/plans/2026-09-29-cldd-strength-1.0-replication.md` and
  `docs/superpowers/plans/2026-09-29-cldd-option-c-segmented-selection.md`.
- **[planned, unchanged]** 0.4.0 release mechanics; reveal-`u` ablation.

## Locked decisions

- **Build now, run later.** The operator's words, in order: "wait for final go
  ahead before building", then "build with subagents". The second was read as
  the go-ahead to build code and run pilots, and NOT as a go-ahead to run either
  matrix. Reason: a fresh seed is spent the moment it runs, and the hypothesis
  wording has not been ratified. A matrix run needs its own explicit go.
- **Grid and family constants are provisional.** The drivers carry the
  recommended fork values. Reason: the operator has not ruled. Every fork except
  F8 lands as a constant change; F8 (strength-0 cells for segmented selection)
  is a driver revision.
- **Hypothesis wording is the operator's.** Reason: the session that drafted it
  had already seen a one-seed feasibility spike on seed 42, and the pilot's
  round counts on seed 1000.
- **The replication's seeds are `{5000 + 16i}`; `{1000 + 16i}` is spent.**
  Reason: the strength-1.0 observation was read off the spaced set after the
  data was in. Every committed artifact's seeds are at or below 2026 and a loop
  run consumes at most seed + 1007.
- **The replication pilot runs on a spent seed, never a fresh one.** Reason: the
  pilot must not expose a confirmatory outcome. It byte-matches the driver
  against the committed `surface_frontier.csv` instead.
- **A suffixed manifest gets a suffixed file; the committed
  `artifacts/surface_env.json` is never rewritten.** Reason: it is a
  hash-pinned record of the 2026-08-04 re-baseline.
- **Functions that write take their target as a required argument.** Reason:
  see the 09-29 learnings entry on default output paths. Three instances in one
  day.
- **Test count was synced at the end of the build (316), not deferred to the
  results tasks.** Reason: a green, pushable tree. This departs from the 08-20
  lock "counts sync once, after the last test lands"; the results tasks will add
  four doc-gate tests and sync again.
- **Spike findings stay out of this ledger.** Reason: they are one-seed design
  inputs, recorded in the spec draft with their disclosure. Publishing them here
  would pre-announce an experiment that is not registered.

## Reuse map

- `src/cldd/selection.py` — `knockout_rates(depth, approval_rate)` builds a
  rate tuple that preserves the overall approval rate; `validate_policy` is the
  one constructor-time check both generators share.
- `scripts/run_surface_sweep.py` — both new drivers import its `_FR_CHILD`,
  `_run_child`, `_append`, `_done_keys`, `_rows_by_key`, `_string_match`. Do not
  copy them.
- `scripts/surface_stats.py` — the replication stats import `frontier_by_seed`,
  `hs1_row` and the never-passed encoding. `hs1_row` reads the world from the
  hypothesis name's last letter, so names must end in `f` or `s`.
- `scripts/feedback_sweep_stats.py` — `sign_test`, `wilcoxon_test`,
  `holm_adjust`. One implementation for v3, v4 and both new scripts.
- `tests/test_doc_numbers.py::_perturbed_rows` and the row-drop pattern — the
  non-vacuity harness the results tasks must extend.
- The build-only plan,
  `docs/superpowers/plans/2026-09-29-cldd-world-testing-build.md` (local), and
  its verdict log beside it. The two parent plans fail the plan executor's
  intake as written, because operator gates and run steps carry no file list.
  A build-only plan is the shape that executes.

## Invariants

- **No matrix without a ratified, committed spec and an explicit go.** Running
  `run_strength_replication.py` or `run_segment_sweep.py` without `--pilot`
  spends seeds that cannot be unspent.
- **`selection_policy=None` is byte-identical to the pre-knob path.** The
  policy consumes no randomness. Breaking either breaks every published number.
- **Every policy in the grid preserves the 0.60 approval rate.** The generators
  refuse a policy whose mean rate differs.
- **The legacy cell passes no generator kwargs at all.** It is the byte-identity
  embed cell; a test pins the child code for it.
- **A new test file ends with a count re-sync.** The doc gate prints the literal
  it expects.
- **`artifacts/SHA256SUMS.json` changes whenever a tracked artifact is added.**
  Both matrices will add two; re-pin in the same change.
- **Run everything with `.venv/Scripts/python.exe`.** The machine's bare
  `python` carries scikit-learn 1.8.0 and fails five pinned tests on any commit.
- **After moving the checkout, reinstall with `pip install -e . --no-deps`.**
- **`src/cldd/scm.py` is checked out CRLF.** Edit in place.
- Dated docs and ledger entries stay untouched. Three older learnings entries
  fail `check-learnings` on format and were failing before this session; they
  are immutable and were left alone.

## Open / next

1. **Operator: commit the build, or hold it.** Command block in the session
   close-out. The repo's contract is spec first; pushing now puts experiment
   code in a public repo ahead of its spec.
2. **Operator: rule on the forks and finalize both hypothesis families.** Then
   each spec moves into `docs/superpowers/specs/` and is committed.
3. **Strength-1.0 matrix first**, about 25 minutes, then its analysis and
   skeptic pass. Known risk, stated before the data: on the spent seeds the SCM
   contrast sits exactly on the floor.
4. **Segmented-selection matrix second**, about 70 minutes. If F8 is adopted,
   revise the driver first.
5. **Reveal-`u` only if strength-1.0 replicates**, and then at strength 1.0.
6. **Essay.** The draft's closing commands should compare
   `artifacts/surface_env.json` with `artifacts/surface_env_mine.json`; its pin
   moves from `36752b0` to the commit it is published against.
7. **Reviewer findings carried, not fixed**: the spent-seed guard checks the 25
   seeds but not the ranges their runs consumed; an inclusive cutoff can fund a
   segment slightly above its rate on tied scores; the SCM cohort's generator
   back-reference gains an attribute, so a pickle of the whole cohort object is
   not byte-identical although the generated data is.

## Evidence

Subagent run: one wave, 12 agents, all receipts on their pinned models, dispatch
check clean. Four task reviews PASS/APPROVED on the first round. Three
whole-branch skeptics: two `true`, one `refuted` on a single clause, from a run
under the wrong interpreter (learnings entry, 09-29). The workflow's own
`claimTrue` is therefore false; the orchestrator's rerun under the pins is the
evidence for that clause.

Replication pilot, 2026-09-29, tree as described above:

```
PILOT GATE (strength replication) -- spaced seed 1000 only
loop pilot flat@0.0 seed=1000 ...
  4 rounds in 17 s
loop pilot flat@1.0 seed=1000 ...
  4 rounds in 22 s
loop pilot scm@0.0 seed=1000 ...
  4 rounds in 12 s
loop pilot scm@1.0 seed=1000 ...
  4 rounds in 11 s

PILOT GATE PASS -- byte-match to the committed surface + budget hold; matrix may launch
```

Segmented-selection pilot, same tree:

```
PILOT GATE (Option C) -- seed 1000 only
env: matches artifacts/surface_env.json
isolation: knockout vs legacy cohorts, both worlds ...
loop pilot legacy [flat] seed=1000 ...
  4 rounds in 7 s
loop pilot aggregate_credit_utilization:high:d0.0 [flat] seed=1000 ...
  4 rounds in 7 s
loop pilot aggregate_credit_utilization:high:d1.0 [flat] seed=1000 ...
  3 rounds in 6 s
loop pilot legacy [scm] seed=1000 ...
  4 rounds in 11 s
loop pilot aggregate_credit_utilization:high:d0.0 [scm] seed=1000 ...
  4 rounds in 11 s
loop pilot aggregate_credit_utilization:high:d1.0 [scm] seed=1000 ...
  3 rounds in 9 s

PILOT GATE PASS -- byte-match + isolation + non-vacuity + budget all hold; matrix may launch
```

The segmented-selection pilot prints round counts for a confirmatory seed. That
exposure is disclosed in the spec draft.
