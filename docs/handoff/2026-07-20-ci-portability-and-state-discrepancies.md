# Handoff — CI portability fix and the day's state discrepancies

*2026-07-20. Newest commit described: **`7f03f52`** (`ci: drop full-history clone
from the docs job`). Measure drift from there.*

This session began as "pick up work on CLDD" and became a CI repair: `master`
had been red for a day and no record said so. The v3 science was re-verified and
survived unchanged; what broke was the *instrument*, not the result.

## Current state

- **[built + landed + CI-verified]** Differential default-path identity test —
  `1d209d4`. Replaces a machine-derived sha256 literal. Reconstructs
  `feedback.py` from git blob `da81c98`, loads it as `cldd._prev3_feedback`, and
  compares both runs **in one process**, so it is invariant to the platform's
  floats.
  *re-verify:* `.venv/Scripts/python.exe -m pytest -q tests/test_feedback_flags.py` (8 passed)
- **[built + landed + CI-verified]** `fetch-depth: 0` on the three CI jobs that
  run pytest (`1d209d4`), and *not* on `docs`, which runs sphinx only
  (`7f03f52`). Without it `actions/checkout` clones at depth 1, the blob is
  unreachable, and the gate silently skips.
  *re-verify:* `python -c "import yaml;d=yaml.safe_load(open('.github/workflows/ci.yml'));[print(n, [s for s in j['steps'] if 'checkout' in str(s.get('uses',''))][0].get('with',{}).get('fetch-depth'), 'pytest' in ' '.join(str(s.get('run','')) for s in j['steps'])) for n,j in d['jobs'].items()]"`
- **[built + landed]** Module-scoped fixtures sharing the pre-v3 module and the
  baseline run — `0c9f7bf`. Blob exec'd once, baseline loop run once per module
  (3 heavy runs, was 4). Behaviour-neutral; re-mutation-tested after the change.
  *re-verify:* `.venv/Scripts/python.exe -m pytest -q tests/test_feedback_flags.py --durations=4`
- **[verified]** **CI is green on `7f03f52`: all 15 jobs, 0 non-success**, run
  29769486987. Green was checked for vacuity, not merely read — `pinned-repro`
  reports 194 passed / 9 skipped, the same skip count as the last pre-v3 green
  run (`8e8f914`, 140 + 9). See
  [[../learnings/2026-07-20-green-ci-must-be-checked-for-vacuity]].
  *re-verify:* `gh run list --limit 1 --json headSha,conclusion`
- **[verified]** v3 results unchanged and recomputed from the committed
  artifact, not quoted: H1 CONFIRMED (median −0.0028, 24/25, Holm 2.325e-06,
  clears the 0.0018 floor); H2 opposite-sign (+0.0119, 0/25); H3/H3a negative;
  H4 identity max abs error 1e-10 over 300 checks per severity.
  *re-verify:* `.venv/Scripts/python.exe scripts/feedback_sweep_stats.py`
- **[verified]** Full suite **203 passed** under pins; `sphinx -W` clean.
  *re-verify:* `.venv/Scripts/python.exe -m pytest -q`
- **[built, UNCOMMITTED]** This brief, the learnings ledger under
  `docs/learnings/`, and a `CLAUDE.md` correction (stale `123 passed` → `203`).
- **[planned]** 0.3.0 PyPI release — **unblocked**; only the checklist remains.
- **[not started]** Spec §9 deferred: Option A (`unobserved_strength` × severity
  frontier surface) and Option C (structured/segmented selection policies).

## Locked decisions

- **Differential comparison, not a re-frozen constant.** Re-pinning the hash on
  Linux was considered and rejected: it would still encode one environment's
  floats and would make the gate unrunnable on the author's Windows machine.
  *Reason to check:* holds as long as `pinned-repro` runs on `ubuntu-latest`
  while development happens on Windows.
- **The identity test carries no `pinned` marker, deliberately.** Under the
  differential design it is platform-invariant, so it belongs in the compat
  matrix. *Reason to check:* only valid while both sides run in the same
  process under the same libraries — reintroducing any stored constant flips
  this and the marker becomes mandatory.
- **Tolerances were never loosened.** The two gate catches during the v3 firing
  were fixed by spec amendment: Rev 2.1 (pricing basis — full-cohort
  denominator) and Rev 2.2 (identity columns stored at `round(10)`; `round(4)`
  had quantized H4 below its 1e-6 tolerance).
- **H2's sign is reported as measured.** It came out opposite to the
  pre-registered direction and stays that way.
- **Dated docs stay dated.** `docs/assessment.md` (Parts I *and* II) and
  `SESSION_HANDOFF.md` are provenance snapshots; their test counts are frozen on
  purpose. `CLAUDE.md` is *not* such a file and must track reality — see
  [[../learnings/2026-07-20-adding-a-test-invalidates-every-quoted-suite-count]].
- **`TARGET_DECLINED_ECE = 0.10` is a registered defect, not defended.** v3 uses
  the alarm because it is what the harness does. Out of scope per spec §9.
- **Git history belongs to the operator.** This session output commit commands;
  the operator ran them. That is why a pick-up must check `gh run list` and not
  assume a handed-over command was run — see
  [[../learnings/2026-07-20-session-state-records-drifted-from-the-repo]].

## Reuse map

- `_load_pre_v3_feedback` (`tests/test_feedback_flags.py`) — general recipe for
  running an old module beside the new one: `spec_from_loader` +
  `__package__ = "cldd"` + `exec` of a `git show` blob. Reuse for any future
  cross-version identity check rather than storing another constant.
- `pre_v3_feedback` / `baseline_hash` fixtures (same file) — module-scoped;
  extend these rather than re-running the baseline loop in a new test.
- `_serialize_v1_fields` / `_hash_v1_fields` — hash only pre-v3
  `GenerationResult` fields, so they stay valid against both object shapes.
- `scripts/feedback_sweep_stats.py` — the **only** source for v3 figures;
  recomputes everything from `artifacts/feedback_sweep.csv`.
- Docs slots: `docs/how-it-works.md` (mechanics), `docs/validation.md` (gates),
  `docs/configuration.md` (knobs). Long-form never returns to the README.

## Invariants

- Never modify `artifacts/*.csv`, the frozen determinism baselines, or headline
  claims.
- Byte-determinism per seed; all randomness through seeded
  `numpy.random.Generator` streams (levers seed from `ctx`, never a global RNG).
- `CalibratedPDClassifier.predict_proba(X)[:, 1]` stays byte-identical to
  `train_pd_model(...).predict_pd(X)` (test-enforced).
- **Do not add an unmarked float-exact-against-a-constant test.** That is
  precisely what broke CI for a day. If a comparison must be float-exact, make
  it differential or mark it `pinned`.
- `fetch-depth: 0` must stay on every CI job that runs pytest. Removing it makes
  the identity gate skip and go vacuously green.
- Gates that must stay green: `pytest` (**203** under pins; 194 + 9 skipped on
  public CI), `pytest --cov=cldd`, `sphinx -b html -W` (0 warnings; no mermaid
  fences in `docs/*.md`), wheel ships `cldd/py.typed`.
- `_check_sample_weight` is private sklearn API — watch on sklearn major bumps.

## Open / next

1. **Commit this brief, the learnings ledger, and the `CLAUDE.md` fix.** They sit
   untracked; `docs/handoff/` and `docs/learnings/` were created this session and
   are new to the repo. Commit command is with the operator.
2. **0.3.0 release, no blocker left.** Flip `CITATION.cff` to 0.3.0, date the
   CHANGELOG header (currently "2026-07-19 (alpha, unpublished)"),
   `pip install -e ".[dev]"` to clear the stale 0.1.0 metadata, push tag
   `v0.3.0`, then verify-the-effect from a clean venv
   (`pip install closed-loop-default-detection` → 0.3.0). Trusted publisher
   carries over from 0.1.0/0.2.0 — no re-registration.
3. **`docs/superpowers/plans/2026-07-14-cldd-v3-feedback-profit.md` is still
   untracked** — the v3 implementation plan, companion to the committed spec
   (`b23dc01`). Operator's call whether it ships as provenance; not staged.
4. **Optional, cheap:** restore a local Linux loop (start Docker Desktop, or
   `sudo apt install python3.12-venv` in WSL Ubuntu) so the next
   platform-specific CI failure doesn't cost a push cycle —
   [[../learnings/2026-07-20-no-local-linux-reproduction-on-this-machine]].
5. **Deferred, named, not dismissed:** spec §9 Options A and C.
