---
ts: 2026-07-20T18:55:44Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: verified
---

**fact:** Every out-of-band record of this repo's state was wrong on
2026-07-20, in a different direction each — which is why pick-up re-verifies
instead of reading. Three concrete discrepancies:

1. **Carried session state said the v3 work was "0.3.0 staged, commit pending
   operator."** It had been committed and pushed the day before.
2. **`HANDOFF.md` was two releases stale** — headed *"Written 2026-07-02,
   master at `3eedb13`"*, describing the 0.1.0 sklearn-wrapper session, while
   the repo was at v3/0.3.0. Its "Open / next" pointed at work long since done.
3. **Nothing anywhere recorded that CI was red.** `master` had been failing
   14/15 jobs since `9996832` (2026-07-19) — through the sweep, the docs, and
   the version bump. Neither the handoff, the CHANGELOG, nor the carried state
   mentioned it.

**basis:** for (1), both commits were already in `origin/master`:

```
$ git log --oneline 75934ba~1..f2f1123
  f2f1123 2026-07-19 14:04:27 -0400 docs: v3 results (H1 confirmed, H2 opposite-sign, H4 exact); bump 0.3.0
  75934ba 2026-07-19 14:04:26 -0400 feat: v3 450-run sweep artifact (round(10) identity columns, spec Rev 2.2)
$ git branch -r --contains f2f1123   ->   origin/master
```

for (3), the archived run conclusions:

```
$ gh run list --limit 5 --json headSha,conclusion
  f2f1123 failure   2026-07-19T18:04:30Z
  9996832 failure   2026-07-19T16:11:51Z
  8e8f914 success   2026-07-14T22:27:58Z     # last green before the v3 core
```

for (2): basis captured against the working tree at `f2f1123`, **pre-dates this
entry's anchor** — the stale `HANDOFF.md` was overwritten by this session's
rewrite, so its 2026-07-02 header no longer exists in the tree and cannot be
re-captured. The commit dates above independently corroborate the gap.

**Standing consequence:** finishing a session by handing the operator commit
commands means the *next* session cannot assume those commands were run, nor
that the resulting CI was watched. Check `gh run list` at pick-up, not just
`git status`.

**re-verify:** `gh run list --limit 6 --json headSha,conclusion,createdAt --jq '.[] | "\(.headSha[:7]) \(.conclusion) \(.createdAt)"'`
