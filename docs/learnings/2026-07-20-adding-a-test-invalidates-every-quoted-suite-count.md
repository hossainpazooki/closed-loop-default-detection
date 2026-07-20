---
ts: 2026-07-20T18:57:58Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: verified
---

**fact:** The suite count is quoted in several places and goes stale silently.
Adding one test invalidates all of them, and *this session did exactly that* —
the new non-vacuity guard took the suite 202 -> 203. Two live discrepancies
found as a result:

1. **A near-miss of my own:** the refreshed handoff was drafted asserting
   "202 passed" as *verified on the fixed tree* while the run had not returned
   and the added test had already made 202 wrong. Caught and corrected before
   the brief was handed over. Writing a count from expectation rather than from
   a completed run is the failure mode.
2. **`CLAUDE.md` was stale by 80 tests** — it read `# 123 passed under pins`,
   a 0.1.0-era figure, through both the v2 (149) and v3 (203) expansions.
   Corrected in this session to 203, with the 9 CI skips noted inline.

**basis:**

```
$ .venv/Scripts/python.exe -m pytest --collect-only -q | awk -F': ' '/^tests\/.*: [0-9]+$/ {s+=$2} END {print s}'
  203
$ grep -rn "123 passed\|149 passed" CLAUDE.md docs/*.md
  CLAUDE.md:25:pytest      # 123 passed under pins          <- STALE, fixed
  docs/assessment.md:421:pytest   # 149 passed              <- dated snapshot, LEFT ALONE
```

**The distinction that matters:** `CLAUDE.md` is a live instruction file and must
track reality; `docs/assessment.md` and `SESSION_HANDOFF.md` are dated provenance
snapshots whose counts are *deliberately* frozen — "never fix their test counts"
is a locked decision. Do not sweep counts globally.

**re-verify:** `.venv/Scripts/python.exe -m pytest --collect-only -q | awk -F': ' '/^tests\/.*: [0-9]+$/ {s+=$2} END {print s}'` and confirm it matches the number in `CLAUDE.md`
