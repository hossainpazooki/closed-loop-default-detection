# The v3 raw sweep CSV was never committed — found by the gate's first CI run

*2026-07-29. Status: verified (CI red on 14/14 pytest jobs, single cause;
fixed same day).*

## What happened

The doc-number gate went red on its first CI run: its `feedback-hypotheses`
claim recomputes the v3 verdicts from `artifacts/feedback_profit_sweep.csv`,
and that file did not exist on CI. It had existed locally since 2026-07-19
(where the sweep ran) but was **gitignore-default-denied** (`artifacts/*` with
no `!` exception) — so v3's own README claim, "every number below recomputes
via `python scripts/feedback_sweep_stats.py`", was broken on every clone since
v3 shipped. `feedback_sweep_stats.csv` was untracked too. Nobody noticed for
ten days because every consumer of those numbers ran on this machine.

## The fix, and the mechanization

Both CSVs committed (with `!artifacts/...` exceptions). More importantly the
class is now mechanized: `check_doc_numbers.py` declares `ARTIFACTS_READ`, and
`tests/test_doc_numbers.py::test_gate_artifacts_are_git_tracked` asserts every
declared artifact is **git-tracked, not merely present** — which fails
locally, before a push, when a claim starts reading a local-only file.

## The lesson

This is the repo's **third** unexcepted-artifact incident (the unanchored
`HANDOFF.md` exclude, 2026-07-22; the spaced CSVs caught pre-push,
2026-07-29; now the v3 raw sweep). Under a default-deny ignore rule,
"the file is in `artifacts/`" and "the file ships" are different claims, and
only a tracked-status probe distinguishes them (cf. the 07-24
empty-diff-only-valid-for-tracked-paths lesson). A fail-closed gate that reads
files must pair with a guard that those files are tracked — otherwise the
gate's first honest act is to fail somewhere you can't see.
