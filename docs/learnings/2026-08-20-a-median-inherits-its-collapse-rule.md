# a median inherits its collapse rule

ts: 2026-08-20T17:43:55Z
commit: 9ff50a9
session: cldd-article-and design-update (Claude Code, 2026-08-20; gate-hardening execution, Task 2)
status: verified
fact: A new verb-guard assert compared the spaced SCM frontier median against a median over ALL frontier_sweep.csv rows (86 iteration rows, median 0.4) instead of first collapsing to one terminal value per seed (25 values, median 0.2 - the statistic the README actually quotes), and so concluded the "does not replicate" verb no longer held, refusing a TRUE claim. The gate fired on real data and caught its own author's plan snippet. Same defect class as Rev 1.1's wrong-cell figure: a summary statistic silently computed on a different basis than the pipeline's. Before comparing anything against a published median, reproduce the pipeline's own collapse (here: claim_frontier_distribution's by-seed dict), never a raw-row shortcut.
basis: recompute at 9ff50a9: "uncollapsed n=86 median=0.4 | collapsed n=25 median=0.2"; the failing state was gate output "FAIL spaced-replication UNEVALUABLE: AssertionError: README 'does **not** replicate' verb: spaced and original SCM medians now agree" (captured at 3082d9b + uncommitted Task-2 tree, pre-dates this entry's anchor); fix landed in cec08ae with the basis documented in a comment.
re-verify: .venv/Scripts/python.exe -c "import csv; rs=[r for r in csv.DictReader(open('artifacts/frontier_sweep.csv')) if r['generator']=='scm']; a=sorted(float(r['frontier_severity']) for r in rs if r['frontier_severity'] not in ('','None')); b={}; [b.__setitem__(int(r['seed']), r['frontier_severity']) for r in rs]; c=sorted(float(v) for v in b.values() if v not in ('','None')); print(len(a), a[len(a)//2], len(c), c[len(c)//2])"
