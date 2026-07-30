# Handoff — v4 spec committed; the gate's first CI run caught a ten-day-old hole

*2026-07-29, second entry this date (the [first](2026-07-29-part-iii-spaced-rerun-and-doc-number-gate.md)
was committed before these events). Written on `eb9397b` (v4 spec commit) +
this fix's uncommitted changes; commit commands output to the operator.*

## Current state

- **[verified] v0.3.0 is fully shipped** — probed fresh this session: PyPI
  serves 0.3.0 (`author_email: None`), GitHub Release live on tag `v0.3.0`
  (published 2026-07-22T18:01Z), pyproject/CITATION/editable-install all
  0.3.0, CHANGELOG dated.
  *re-verify:* `curl -s https://pypi.org/pypi/closed-loop-default-detection/json`
  · `gh release view v0.3.0` · `pip show closed-loop-default-detection`
- **[built + committed] v4 Option A spec** at
  `docs/superpowers/specs/2026-07-29-cldd-v4-option-a-surface-design.md`
  (`eb9397b`): purpose (coincidence → intervention), operator decision record
  (both surfaces; 6-point grid {0, .2, .4, .55, .7, 1.0}; hybrid CF protocol),
  two additive knobs, confirmatory family m=4 with floors, 300+450 runs
  ~27.5h, pilot + byte-identity embed gates. **The implementation plan was NOT
  started** (writing-plans interrupted for this handoff) — next session starts
  there, from the spec.
- **[built, uncommitted] CI-red fix.** The doc-number gate's first CI run
  failed all 14 pytest jobs (both 07-29 pushes) with a single cause:
  `artifacts/feedback_profit_sweep.csv` was **never committed** —
  gitignore-default-denied since v3, invisible locally because the sweep ran
  on this machine. v3's "recomputes from a committed CSV" README claim was
  clone-broken from the start. Fix: both feedback CSVs get `!` exceptions and
  are committed; `check_doc_numbers.py` now declares `ARTIFACTS_READ` and a
  guard test asserts each is **git-tracked, not merely present** (fails
  locally pre-push next time). Suite is now 209 collected; locally 208 pass +
  the tracked-guard red **by design until the CSVs are committed** — the
  operator's commit is the fix. Full record:
  `docs/learnings/2026-07-29-v3-raw-sweep-was-never-committed.md` (third
  unexcepted-artifact incident).
  *re-verify (post-commit):* `pytest tests/test_doc_numbers.py -q` (6 pass) ·
  CI on the pushed tip goes green
- **[unchanged]** Everything in the first 07-29 brief (spaced-rerun results,
  premise correction, gate catches) except the test count (now 209).

## Locked decisions

All prior locks hold, including the three v4 spec decisions (operator's, in
the spec's decision record). New: **`ARTIFACTS_READ` is the gate's artifact
manifest** — a claim reading a new file adds it there + a gitignore exception
+ `git add`, same change.

## Open / next

1. **Operator: run the two commits + push**; confirm CI green on the tip
   (that is the fix's real gate — the local red is by design pre-commit).
2. **Next build session: v4 implementation plan** via writing-plans, from the
   committed spec; then build per the repo contract. Plan stays local
   (gitignored).
3. Unchanged options: essay-URL pointer; local Linux loop; essay's
   "SCM median 0.2" annotation (operator's call).
