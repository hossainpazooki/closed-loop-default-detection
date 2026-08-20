# Handoff — Gate hardening landed: 13 claims, mutation self-test, verb guards, hash pins

*2026-08-20. Written on `9ff50a9` (pushed, CI green — run 32398257135, 15/15, the
first CI execution of the mutation and integrity layers). Pick-up measures drift
from `9ff50a9`; this brief plus four learnings entries and their index rows are
the only uncommitted cldd files at close.*

## Current state

- **[built] The doc-number gate is 13 claims and self-proving.** Three new
  `docs/validation.md` claims (`surface-run-counts`, `pinned-environment`,
  `suite-counts` — the last caught a stale "149 tests" that had drifted to 246);
  scope is now README + validation.md living figures. Every artifact-backed
  claim carries a continuous non-vacuity test: value-mutation for claims that
  quote measured values, row-drop for `surface-run-counts` (value-insensitive by
  construction — see the 08-20 learnings entry), a load-shim mutation for the
  feedback claim, plus a harness-vacuity test proving the mutation detector
  itself can fail.
  re-verify: `python scripts/check_doc_numbers.py` → 13 PASS, exit 0 ·
  `python -m pytest tests/test_doc_numbers.py -q` → 18 pass
- **[built] Qualitative verbs are now conditional.** `claim_counterfactual_headline`
  and `claim_spaced_replication` refuse their literals unless re-derivation
  supports "cuts MAE", "the effect survives", "collapses to a negligible", and
  "does **not** replicate" (constants `ALPHA=0.05`, `MAJORITY=13`,
  `NEGLIGIBLE_FRACTION=0.5`, commented as verb operationalizations). Refusal
  proven by sign-flip tests. The replicate-guard compares per-seed collapsed
  medians — the raw-row shortcut reads 0.4 where the pipeline's statistic is
  0.2 (bug caught live; learnings entry).
  re-verify: `python -m pytest tests/test_doc_numbers.py -q -k refuses` → 2 pass
- **[built] Artifact content-hash pins.** `artifacts/SHA256SUMS.json` (22
  entries, committed) + `scripts/pin_artifacts.py`; sha256 over LF-normalized
  bytes (index stores LF, Windows worktrees check out CRLF — raw-byte hashes
  would be platform-dependent). A silent artifact edit now fails CI even when a
  doc is edited to match; a manifest-line change is the review surface.
  re-verify: `python -m pytest tests/test_artifact_integrity.py -q` → 4 pass
- **[built] Essay A executable figure registry** (dev-root repo,
  `~/dev/briefs/scripts/check_essay_figures.py`; **uncommitted there by the
  operator's choice**). Five Class-G claims; `surface_stats.csv` refused by
  name (`FORBIDDEN` set); modes `--list` / `--self-test` / `<draft.md>`; run
  with the cldd venv (scipy). Self-test: clean-pass=True tamper-fires=True.
  re-verify: `cd ~/dev/briefs && ~/dev/closed-loop-default-detection/.venv/Scripts/python.exe scripts/check_essay_figures.py --self-test`
- **[built] The I-1 field-pair basis is reconciled.** The registry recomputed
  2,413 vs the evidence pack's 3,062; decomposition: 3,062 = **2,044
  discriminating** + 649 join-key pairs (equal by construction) + 186
  blank-vs-blank + 183 constant-column. Reconciliation appended to the evidence
  pack §3 (skeptic's table verbatim), outline corrected in both places, registry
  emits 2,044. Verdict (0 mismatches) unchanged.
  re-verify: the learnings entry's one-liner → `3062 649`
- **[verified] Everything is landed and green**: commits
  `cca5281`/`cec08ae`/`0764c4a`/`9ff50a9` pushed, 0 ahead/0 behind, suite 246
  collected exit 0, sphinx `-W` exit 0, CI 15/15 on the tip.
  re-verify: `gh run list --limit 1 --json conclusion,headSha`
- **[planned, unchanged priorities]** Essay A drafting (next); 0.4.0 release
  mechanics; reveal-`u` ablation (spec §10's "revisit after the surface is
  read" condition is now met); strength-1.0 pre-registration; optional
  assessment Part IV.

## Locked decisions

- **Verb operationalizations are named constants with comments, in one place**
  (`ALPHA`/`MAJORITY`/`NEGLIGIBLE_FRACTION` after `SEVERITY_GRID`). Reason:
  prose verbs need explicit numeric meaning to be gateable; scattering or
  hard-coding them makes the next drift invisible.
- **Hashes are over LF-normalized bytes.** Reason: `git ls-files --eol` shows
  `i/lf w/crlf` — raw-disk hashing breaks on the first platform mismatch. The
  digest pins content, not checkout convention.
- **Gate scope = README + validation.md living figures; CHANGELOG and dated
  docs stay excluded.** Reason: the gate docstring's own rule — dated docs are
  frozen provenance and gating them would be wrong at the first legitimate
  supersession. The 51/51 fidelity figure stays unregistered: its text declares
  it "dated, not standing".
- **Essay A quotes 2,044, not 3,062, when claiming verification power.**
  Reason: 1,018 of the 3,062 compared pairs could not have failed (join keys /
  blanks / constant column); quoting them as verification inflates the claim —
  the exact defect class the essay is about. 3,062 is quotable only as "pairs
  compared" with the basis stated.
- **Misfit non-vacuity probes get exempt-with-reason + a matching probe, never
  a weakened harness.** Reason: weakening the harness to admit one claim
  silently weakens it for all (see the row-drop learnings entry).
- **Doc test-count literals sync once, after the last test lands.** Reason:
  adding a parametrize entry moves the count; syncing mid-sequence produces
  churn and a false green (230→239→241→245→246 this session).

## Reuse map

- `tests/test_doc_numbers.py::_perturbed_rows` / `_fires_under_mutation` /
  `_ARTIFACT_BACKED` — the mutation harness; add new value-quoting claims to
  the list, key columns to `_KEY_COLS`.
- `tests/test_doc_numbers.py::test_surface_run_counts_fires_on_dropped_run` —
  the row-drop pattern for count-of-keys claims.
- `scripts/pin_artifacts.py` — rerun ONLY on legitimate artifact addition or
  documented supersession; the manifest diff is the review surface.
- `~/dev/briefs/scripts/check_essay_figures.py` — extend its `CLAIMS` list at
  drafting; literal wording finalizes with the draft in the same change
  (07-29 lock).
- `docs/superpowers/plans/2026-08-20-doc-number-gate-hardening.md` (local) —
  executed plan with a 7-entry deviation log; read it before trusting any
  claim about how this session went.

## Invariants

- The gate is **13 claims**; a new figure in README or validation.md must be
  registered same-change, and a new test file must end with a count re-sync
  (the gate itself prints the correct literal on failure).
- `artifacts/SHA256SUMS.json` must stay git-tracked and must change whenever
  any tracked artifact changes — `test_artifact_integrity.py` fails CI
  otherwise. Never edit an existing entry without its supersession reason.
- I-1 fail-closed guards and the mutation/refusal tests are load-bearing; do
  not "simplify" them away.
- Class-G/H partition still governs Essay A reads (README v4 section,
  how-it-works v4 section, both 08-18 briefs' marked tails, `surface_stats.csv`).
- `docs/assessment.md` and all dated docs stay untouched; ledger entries are
  immutable (supersede with `kills:`).

## Open / next

1. **Operator: commit this brief + the four learnings entries** (single docs
   commit; command block in the session close-out). The briefs-repo files
   (outline, evidence pack, registry script) remain uncommitted there — that
   was the operator's explicit choice at review; revisit only if wanted.
2. **Essay A drafting session**: `/rigor:pickup` → writing-plans against
   `~/dev/briefs/2026-08-18-essay-a-outline.md`. All publication-checklist
   inputs green, including CI. The registry script is ready to gate the draft;
   the 2,044/3,062 reconciliation is itself quotable Essay-A material.
3. **Watch item, no action**: pandas-intersphinx 503 flake (one occurrence,
   rerun green). Second occurrence → suppress that warning class or vendor
   objects.inv in `conf.py`.
