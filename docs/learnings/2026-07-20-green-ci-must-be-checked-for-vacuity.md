---
ts: 2026-07-20T18:54:06Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: verified
---

**fact:** A green `pinned-repro` is not by itself evidence the identity gate
ran. The differential test **skips** when the pre-v3 git blob is unreachable,
and `actions/checkout` defaults to `fetch-depth: 1` — so without the explicit
`fetch-depth: 0`, every job would have skipped the gate and reported green
having tested nothing. Read the skip count, not just the tick.

**basis:** the skip count is the discriminator. It is unchanged at 9 between the
last pre-v3 green run and the post-fix green run, while the pass count rose by
54 — so all 54 new v3 tests, the three identity tests included, actually
executed:

```
$ for sha in 8e8f914 1d209d4; do ... pinned-repro log | grep 'passed, .* skipped'; done
  8e8f914: 140 passed, 9 skipped     # pre-v3 (0.2.0); 140+9 = documented 149-test v2 suite
  1d209d4: 194 passed, 9 skipped     # post-fix; 194+9 = 203 = local total
```

The 9 are the pre-existing private-data fidelity skips, documented as
not-runnable on public CI. **A green `pinned-repro` reporting 12 skips would mean
the identity gate silently stopped running** — that is the failure this entry
exists to make detectable.

**re-verify:** `jid=$(gh run view $(gh run list --limit 1 --json databaseId --jq '.[0].databaseId') --json jobs --jq '.jobs[] | select(.name|startswith("pinned-repro")) | .databaseId'); gh run view --job=$jid --log | grep -aoE '[0-9]+ passed, [0-9]+ skipped' | tail -1`
