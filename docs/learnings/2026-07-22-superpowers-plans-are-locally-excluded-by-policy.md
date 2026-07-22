---
ts: 2026-07-22T17:50:11Z
commit: 3be6c06
session: 7eb7bd13-dbfd-4bce-bc15-cd0e01c8827a
status: verified
---

**fact:** `docs/superpowers/plans/` is **locally excluded** via
`.git/info/exclude` — operator policy settled 2026-07-22 after three
consecutive sessions carried the untracked v3 plan as an unresolved
"operator's call". Plans (execution scaffolding) never ship; the three
`docs/superpowers/specs/` files remain **deliberately committed** as
load-bearing provenance (the 0.3.0 CHANGELOG cites spec Rev 2.1/2.2). Do not
re-flag the plans dir in future handoffs, and do not un-commit the specs.
A fresh clone sees neither the exclusion nor the plans — both are
machine-local. Policy recorded durably in rigor:
`~/dev/rigor/docs/feedback/2026-07-22-handoff-roundtrip-and-unfolded-item-policy.md`.

**basis:** Captured 2026-07-22T17:50:11Z at `3be6c06`:

```
$ grep superpowers .git/info/exclude
docs/superpowers/plans/
$ git ls-files docs/superpowers/
docs/superpowers/specs/2026-07-13-cldd-v2-emp-design.md
docs/superpowers/specs/2026-07-14-cldd-v3-design.md
docs/superpowers/specs/2026-07-19-wap-firing-evidence.md
$ git status --short | wc -l
0
```

**re-verify:** `grep superpowers .git/info/exclude` (expect `docs/superpowers/plans/`)
