# A summary figure took the discussed cell's value, not the extreme cell's

ts: 2026-08-18T20:26:30Z
commit: 42e2385
session: cldd-article-and design-update (Claude Code, 2026-08-18; capture bracketed by the Task-5a skeptic report at 20:24:17Z and its follow-up at 20:29:26Z)
status: verified
fact: Spec Amendment Rev 1.1's drift table reported the counterfactual leg's max ABSOLUTE difference as 4.16e-17, but 4.1633e-17 is exactly the absolute difference of the worst-RELATIVE cell (`strong_gap`, sev 1.0, seed 1352) — the one cell the amendment's prose walks through by hand. The true leg maximum is 6.939e-17 (`naive_strong`, sev 0.4, seed 1016). When a table is filled in next to a prose discussion of one cell, that cell's number gets promoted into the summary row; the defense is recomputing the extreme from the data at write time, never transcribing it from the narrative. Corrected by Amendment Rev 1.2 (committed `c6a70c1`) before any doc quoted it.
basis: independent recompute of v4env vs 2026-07-29 originals, field-wise over 195 differing numeric fields — "CF max ABS: 6.9389e-17 (('0.4', '1016'), 'naive_strong', '0.09658028223179957', '0.0965802822317995')" and "abs diff of the worst-RELATIVE cell (strong_gap sev1.0 seed1352): 4.1633e-17 -> matches the table's stated cf 'max absolute' 4.16e-17: True". First surfaced by the Task-5a skeptic; re-verified by the lead before recording.
re-verify: .venv/Scripts/python.exe -c "import csv;n={(r['severity'],r['seed']):r for r in csv.DictReader(open('artifacts/seed_sweep_spaced_v4env.csv'))};o={(r['severity'],r['seed']):r for r in csv.DictReader(open('artifacts/seed_sweep_spaced.csv'))};print(max(abs(float(n[k][f])-float(o[k][f])) for k in n if k in o for f in n[k] if f in o[k] and n[k][f]!=o[k][f]))"
