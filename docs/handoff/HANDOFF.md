# Handoff index — `cldd`

Pointers only. Each row links a dated, immutable brief; state and evidence live
in the brief, never here. A later session writes a **new** entry — entries are
never edited once written.

Written by `/rigor:handoff`; read by `/rigor:pickup`, which re-verifies a
brief's claims rather than trusting them.

> Note: the repo-root `HANDOFF.md` is a separate, local-only (untracked) working
> note kept via `.git/info/exclude`. This directory is the durable ledger.

| Date | Brief | Newest commit | One-line |
|---|---|---|---|
| 2026-06-26 | [hackathon-era session handoff (relocated 2026-07-22)](2026-06-26-session-handoff-hackathon-era.md) | — | Pre-ledger provenance note moved out of the repo root at public release; machine paths / dataset location / visibility redacted, all figures frozen. |
| 2026-07-20 | [CI portability fix and the day's state discrepancies](2026-07-20-ci-portability-and-state-discrepancies.md) | `7f03f52` | `master` was red for a day from a machine-derived hash baseline; replaced with a differential in-process identity test, CI green 15/15 and checked for vacuity. |
| 2026-07-22 | [v0.3.0 released; v3 closed out](2026-07-22-v0.3.0-released.md) | `1ab178b` | 0.3.0 live on PyPI and effect-verified from a clean venv (discriminating v3-flags probe); author email dropped forward-only; next work is spec §9 Option A/C. |
| 2026-07-22 | [v4 entry: Option A frontier surface](2026-07-22-v4-entry-option-a.md) | `3be6c06` | Starting ground for v4 — what Option A is (`unobserved_strength` × severity surface), inherited locks, reuse map; nothing built; first action is the adversarial spec. |
| 2026-07-24 | [essay published, remediation landed, Part III](2026-07-24-essay-published-and-part-iii.md) | `f8c9cb2` | Essay figures all recomputed pre-publication; 4-item publication remediation done (relocated handoff, Release v0.3.0, README landing, dated fidelity re-run 51/51); assessment Part III = ranked proposed tests, none run; next = v4 spec or Part III priorities. |
| 2026-07-29 | [Part III path (b): spaced rerun + doc-number gate](2026-07-29-part-iii-spaced-rerun-and-doc-number-gate.md) | `0bc6cd8` (+uncommitted) | Spaced sweeps done: counterfactual survives (22/25, p=1.6e-6), SCM frontier median 0.2 does NOT replicate (0.4 on disjoint seeds); critique-1 premise corrected (loop-only overlap); doc-number gate live in CI, caught 3 stale README figures on maiden run; suite 208 green. Next = v4 Option A spec. |
| 2026-07-29 | [v4 spec + gate CI fix](2026-07-29-v4-spec-and-gate-ci-fix.md) | `eb9397b` (+uncommitted) | v0.3.0 ship-verified; v4 Option A spec committed (plan not started); gate's first CI run found `feedback_profit_sweep.csv` never committed (clone-broken since v3, 14 jobs red) — CSVs committed + tracked-status guard test added; suite 209. Next = v4 plan. |
| 2026-08-18 | [v4 executed end-to-end: matrix, gates, verdicts](2026-08-18-v4-execution-gates-and-verdicts.md) | `42e2385` (+uncommitted) | Matrix 300+450 complete and I-1 held at full scale (skeptic-recomputed, 0/3062 mismatches); Rev 1.2 corrects a Rev 1.1 table figure; §9 gates 1–4,6 evidenced (gate 6 by triple agreement, 28/28); verdicts: all four H-S not confirmed, wall stands at strength 0 — doc qualification is next (Task 7). Also repays the missing 08-05 brief. |
| 2026-08-18 | [Task 7: one-cause claim withdrawn, verdicts registered, I-1 fail-closed](2026-08-18-task7-qualification-and-i1-fix.md) | `90cf40d` (+uncommitted) | Spec §3 honored: README mechanism claim withdrawn as measured, registered v4 section + `surface-verdicts` gate claim (10 claims, conditional "not confirmed" literal); I-1 absent-cell guard + regression test (suite 230); sphinx gate repaired locally (venv had lost `[docs]`); ALL §9 gates discharged. Next = operator commits + Essay A drafting. |
| 2026-08-20 | [Gate hardening landed: 13 claims, mutation self-test, verb guards, hash pins](2026-08-20-gate-hardening-landed.md) | `9ff50a9` (+uncommitted) | Doc gate now 13 claims (validation.md registered; caught a stale 149-test count), every artifact-backed claim has a continuous non-vacuity test (value-mutation, or row-drop for count-of-keys claims), qualitative verbs refuse on re-derivation, artifacts pinned by LF-normalized sha256 manifest; essay-side registry built and the I-1 field-pair figure reconciled (2,044 discriminating of 3,062). Suite 246, CI 15/15. Next = Essay A drafting. |
