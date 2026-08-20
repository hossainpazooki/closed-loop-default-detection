# a non-vacuity count included the comparison's own join keys

ts: 2026-08-20T17:43:51Z
commit: 9ff50a9
session: cldd-article-and design-update (Claude Code, 2026-08-20; surfaced by the essay-side figure registry recomputing 2,413 where the evidence pack said 3,062)
status: verified
fact: The 2026-08-18 skeptic's I-1 non-vacuity figure (0 mismatches over 3,062 field-pairs) counted the complete shared schema INCLUDING the columns the comparison joins on - 649 pairs that are equal by construction of the join and could never have failed. Adding the blanks (186) and constant column (183) the skeptic itself flagged, the genuinely discriminating count is 2,044 - a third lower than the quoted figure. A join-based comparator's field-pair count must exclude its own join keys, or the verification-power claim is inflated. Essay A quotes 2,044 (basis reconciliation in the briefs evidence pack section 3; the skeptic's verbatim table stands unedited).
basis: decomposition recomputed at 9ff50a9 from the two v4env CSVs: "total=3062 keys=649 blank=186 const=183 discriminating=2044" (649 = 183 frontier rows x 3 keys + 50 cf rows x 2 keys); the briefs registry (scripts/check_essay_figures.py --list) now emits "0 mismatches" + "2,044 discriminating field-pairs".
re-verify: .venv/Scripts/python.exe -c "import csv; fr=list(csv.DictReader(open('artifacts/frontier_sweep_spaced_v4env.csv'))); cf=[r for r in csv.DictReader(open('artifacts/seed_sweep_spaced_v4env.csv')) if float(r['severity']) in (0.4,1.0)]; print(len(fr)*len(fr[0])+len(cf)*len(cf[0]), len(fr)*3+len(cf)*2)"
