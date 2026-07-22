---
ts: 2026-07-22T18:03:35Z
commit: 18b846e
session: 7eb7bd13-dbfd-4bce-bc15-cd0e01c8827a
status: verified
---

**fact:** The unanchored pattern `HANDOFF.md` in `.git/info/exclude` — meant
only for the repo-root working note — also matched
`docs/handoff/HANDOFF.md`, so **the durable handoff index was never committed**:
three commits that were supposed to ship it (`ec92b43`, `3be6c06`, `18b846e`)
each carried the dated briefs but silently dropped the index, and `git status`
never warned because excluded files don't appear as untracked. The public repo
served pointer-less briefs for two days. Fixed by anchoring both patterns
(`/HANDOFF.md`, `/CLAUDE.md`); `docs/learnings/LEARNINGS.md` was never
affected (no name collision). General rule: a gitignore/exclude pattern
without a leading `/` matches at **every** directory level — anchor any
pattern that names a root-only file, and after "committing a ledger", verify
the *tracked* content (`git ls-tree`), not the working tree.

**basis:** Captured 2026-07-22T18:03:35Z at `18b846e`:

```
$ git show HEAD:docs/handoff/HANDOFF.md
  fatal: path 'docs/handoff/HANDOFF.md' exists on disk, but not in 'HEAD'
$ git check-ignore -v docs/handoff/HANDOFF.md
  .git/info/exclude:8:HANDOFF.md    docs/handoff/HANDOFF.md
$ git ls-tree HEAD docs/handoff/ --name-only
  (three dated briefs, no HANDOFF.md)
# after anchoring:
$ git check-ignore docs/handoff/HANDOFF.md ; echo $?   ->  non-zero (not ignored)
$ git status --short | grep HANDOFF   ->  ?? docs/handoff/HANDOFF.md
```

**re-verify:** `git ls-files docs/handoff/HANDOFF.md` (expect the path printed once committed; empty means the index is untracked again)
