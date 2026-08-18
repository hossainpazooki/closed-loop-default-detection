# Handoff — v4 executed end-to-end: matrix complete, I-1 held, verdicts triple-checked

*2026-08-18. Written on `42e2385` + this session's uncommitted changes (commit
commands output to the operator). This brief also repays a debt: the 2026-08-05
session built the entire v4 surface toolchain (commits `14b899d`..`4029596`) and
left **no brief** — its work is recorded here, 13 days late. Execution plan (local,
gitignored): `docs/superpowers/plans/2026-08-18-cldd-v4-execution-a-pivot.md`,
whose end-of-file execution log records every deviation.*

> **Essay-A drafting sessions: stop before the final section of this brief.** The
> last section carries the confirmatory verdicts (Class H under the essay
> evidence partition). Everything above it is safe.

## Current state

- **[verified] The six 08-05 commits + README count fix are pushed, CI green.**
  `origin/master` = `42e2385`; CI run concluded success on that exact SHA.
  *re-verify:* `git status -sb` (no ahead/behind) · `gh run list --limit 1 --json conclusion,headSha`
- **[built, 08-05 — recorded here belatedly]** Two additive knobs
  (`generator_kwargs` on the loop; `unobserved_strength` on
  `run_counterfactual_eval`), the resumable sweep driver with pilot gate
  (`scripts/run_surface_sweep.py`), the fail-closed stats script with the I-1
  embed gate (`scripts/surface_stats.py`), and **Spec Amendment Rev 1.1**: the
  pilot's maiden run caught ulp-scale drift against the 07-29 spaced artifacts;
  cause isolated to a CPython build change under identical pins (knobs refuted as
  cause by a pre-knob verbatim rerun); I-1 re-anchored to a same-driver
  re-baseline (`*_v4env.csv`) plus a new environment manifest
  (`artifacts/surface_env.json`), tolerance untouched.
- **[verified] Matrix complete: 300/300 loop runs + 450/450 evals** (spec §9
  gate 3). Driver reported 0 missing keys and the count was independently
  recomputed; zero duplicate keys despite a resumed append (58 pre-existing runs,
  all verified terminated before resume). Wall-clock ≈3 h total, confirming Rev
  1.1's re-based estimate (the original spec's 27.5 h was 15× over).
  *re-verify:* import `run_surface_sweep` and call `_missing_frontier_keys()` /
  `_missing_cf_keys()` — both empty.
- **[verified] §9 gate 2 repaired.** The 08-05 session ran the pilot but recorded
  nothing; a fresh pilot was re-run before the matrix launch and its verbatim
  output recorded (local `HANDOFF.md`, §9-gate-2 section). PASS.
- **[verified] I-1 embed gate held at full scale, adversarially.**
  `surface_stats.py` exit 0. An independent skeptic recomputed the comparison
  with its own code: 100/100 default-strength cells, 3062 field-pairs at full
  repr precision, **0 mismatches**, with non-vacuity established (0 absent cells;
  negative control fires on injected 1-ulp faults).
  *re-verify:* `.venv/Scripts/python.exe scripts/surface_stats.py` → gate PASS
  line + exit 0.
- **[built] Spec Amendment Rev 1.2** — the skeptic pass found Rev 1.1's drift
  table reports the cf leg's max-abs as 4.16e-17; the true value is **6.939e-17**
  (the 4.16e-17 belongs to the worst-*relative* cell, reported in the wrong row).
  Lead re-verified before writing. Conclusions unchanged (still ulp-scale, 0
  differences at 4 dp, 0 outcome flips). Amend-by-revision; Rev 1.1 text intact.
- **[built] New learnings entry**
  `2026-08-18-fail-closed-gate-with-one-leg-that-isnt.md`: `i1_check_frontier`
  silently passes a cell absent from BOTH sides (`0 == 0`, zip iterates zero
  times); the cf leg is correctly fail-closed. Latent — currently unreachable via
  `main()`, but only incidentally. One-line fix + failing test **proposed, not
  applied** (execution plan forbids code changes). Process note: the LEARNINGS.md
  index row was added mid-session, contrary to the ledger header's
  handoff-only rule — content correct, breach acknowledged here rather than
  repeated.
- **[verified] Suite green post-execution** (spec §9 gate 1): see the Task-6 run
  recorded in the session log; 229 collected, 9 private-data skips as documented.
  *re-verify:* `.venv/Scripts/python.exe -m pytest -q`
- **[pending operator] Nothing is committed.** Three surface CSVs are untracked
  (gitignore `!` exceptions exist since `14b899d`); spec Rev 1.2, the learnings
  pair, CHANGELOG, and this brief are uncommitted. **Until the commit lands, none
  of today's results are reproducible off this machine** — the repo's recurring
  failure class, flagged by the skeptic itself.

## Locked decisions (new this session)

- **Evidence partition** (essay program): gate/infrastructure evidence (I-1,
  pilot, completeness, Rev 1.1/1.2) is Class G, quotable by Essay A; confirmatory
  verdicts and `surface_stats.csv` content are Class H, embargoed for Essay B.
  Definition: execution plan, Global Constraints.
- **Rev 1.2 supersedes two Rev 1.1 values** (cf max-abs; "last ulp" phrasing);
  everything else in Rev 1.1 stands.
- **§9 gate 6 is discharged by triple agreement** — script, lead recompute, and
  a fully independent skeptic leg: 28/28 cells identical, rescue probes failed to
  overturn any verdict. The first dispatched skeptic stalled and was replaced;
  the stall and substitution are recorded in the execution plan's log.

## Open / next

1. **Operator: run the three commits + push** (block below); confirm CI green on
   the tip — the artifacts must satisfy the tracked-guard and doc-number jobs.
2. **08-04 plan Task 7** (docs, next session): qualify the mechanism language in
   README/docs per spec §3's falsification statement, register every new quoted
   figure in the doc-number gate **in the same change**, sphinx `-W` clean
   (§9 gate 5). Inputs: `artifacts/surface_stats.csv` + the gate-6 record.
3. **I-1 frontier-leg fix** (build session): failing test + one-line fail-closed
   guard, per the learnings entry.
4. **Essay program** (briefs-side): Essay A is unblocked (I-1 evidence pack +
   skeptic 5a CONFIRMED); Essay B's FIRED branch is unblocked by the gate-6
   record. Roadmap: `~/dev/briefs/2026-08-18-cldd-two-essay-arc-design.md`.

---

## Confirmatory verdicts (CLASS H — Essay-A sessions stop here)

All four pre-registered hypotheses **NOT CONFIRMED**; per spec §3's falsification
statement the "one wall / one cause" narrative is withdrawn pending the Task 7
doc qualification. Triple-computed with 28/28 agreement (H-S1f fails on the
0.2 floor only — 7/7 moved seeds in-direction, Holm p 0.031; the rest fail both
legs). Deeper descriptive findings, lead-verified: median g(v, 0.4) runs
*opposite* the spec's predicted direction (+0.0152 → +0.0135 → +0.0090); and the
frontier wall stands at strength 0.0 (flat 25/25 seeds at 0.4 with the confounder
off, walk reaching 0.8) — the wall's existence is not confounder-caused, though
the axis moves it at strength 1.0 (post-hoc, non-confirmatory). Full record with
doc-language guidance:
`~/dev/briefs/2026-08-18-essay-b-confirmatory-verdicts-CLASS-H.md`.
*re-verify:* recompute per spec §3 from the two surface CSVs (sign + Wilcoxon +
Holm m=4 + floors).
