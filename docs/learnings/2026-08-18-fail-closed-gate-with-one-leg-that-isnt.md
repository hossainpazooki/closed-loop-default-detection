# A fail-closed gate with one leg that isn't (I-1 frontier silent pass)

*2026-08-18. Found by the Task-5a skeptic during the v4 execution's independent
I-1 verification; reproduced by the lead against the project's own functions
before being written down. Latent — it did not fire in any run to date.*

## What

`i1_check_frontier` (`scripts/surface_stats.py`) looks up both sides with
`.get(key, [])` and then compares lengths:

```python
got  = sorted(surf.get((world, default_strength[world], seed), []), ...)
want = sorted(ref.get((world, seed), []), ...)
if len(got) != len(want):
    problems.append(...); continue
for i, (g, w) in enumerate(zip(got, want)):   # zero iterations when both are empty
```

When a cell is absent from **both** sides, `0 == 0` passes the length check and
`zip()` iterates zero times: the cell is silently credited as matching.

`i1_check_cf` does not share the defect — it requires `len(got) == 1 and
len(want) == 1` and reports a problem otherwise.

Reproduced with two nonexistent seeds against the project's own functions:

```
absent cells, frontier leg -> problems: 0   (silent pass)
absent cells, cf leg       -> problems: 4   (fail-closed)
```

## Why it hasn't bitten

`main()` runs `missing_frontier_cells()` first, which fails closed on any absent
**surface-side** cell, so the silent-pass path is currently unreachable end to end.
That protection is **incidental, not designed**: it holds only while `SEEDS`,
`WORLDS`, and `DEFAULT_STRENGTH` stay consistent across two independent checks,
and the completeness pre-check iterates `STRENGTHS × WORLDS` — so a
`DEFAULT_STRENGTH` value that is not in `STRENGTHS` would pass completeness and
land in the silent branch. A publication-blocking gate should not depend on a
different function's iteration set for its fail-closed property.

## The lesson

**A gate is only fail-closed on the legs where absence is distinguishable from
agreement.** This is the same class as
`2026-07-29-v3-raw-sweep-was-never-committed.md` (gate read a file that wasn't
there) and `2026-07-20-green-ci-must-be-checked-for-vacuity.md` (green with
nothing compared): every one of them is a comparison that could not tell presence
from absence. When writing any comparator, ask what it returns on empty input —
and if the answer is "pass," that is a defect regardless of whether the empty case
is currently reachable.

The non-vacuity discipline caught this only because the skeptic was asked for
**cell/row/field-pair counts and a negative control**, not just a pass/fail. A
verifier that reports only "0 mismatches" cannot distinguish this defect from
correctness.

## Fix (proposed, not applied)

One line, matching the cf leg's contract — with a test that fails first:

```python
if not want:
    problems.append(f"{label}: reference cell absent (gate cannot verify)")
    continue
```

Not applied in the 2026-08-18 run: that run was executing
`plans/2026-08-18-cldd-v4-execution-a-pivot.md`, a run-and-gate plan that changes
no code, and this repo writes the failing test first. Filed for the next build
session.
