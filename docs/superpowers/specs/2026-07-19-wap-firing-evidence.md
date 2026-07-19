# 2026-07-19 — v3 sweep publish: three-part credit-rule evidence (WAP firing record)

Anchors: CLDD HEAD `9996832` at write (v3 core commits landed); spec Rev 2.2; orchestrated
from rigor session `0e090857`. This is the CLDD-side runnable record; the rigor-side ledger
entry is `rigor/docs/feedback/2026-07-19-wap-firing-cldd-nonorigin-v3-sweep.md`.

## Part 1 — audit green on the candidate

```
$ .venv/Scripts/python.exe scripts/run_feedback_sweep.py --workers 4
wrote artifacts/feedback_profit_sweep.csv  (5400 rows, 450 runs)          # zero missing keys
$ .venv/Scripts/python.exe scripts/feedback_sweep_stats.py               # exit 0
H1: median=-0.0028 (n=25) sign 24/25 p_holm=2.325e-06; floor=0.0018 -> CONFIRMED
H2: median=+0.0119 sign 0/25 -> not confirmed        # predicted <0; measured opposite
H3: median=-0.0024 sign 0/25 -> not confirmed
H4: severity {0.2,0.4,1.0}: n_checked=300 each, max_abs_error=0.0000000001 -> PASS
```

## Part 2 — the same audit demonstrably red on known-bad state

Staged twin (never the real artifact): +0.001 on 11 frozen/eps0.05/sev0.4/seed1000
`book_profit` rows →
```
severity 0.4: n_checked=300 max_abs_error=0.0010000000 -> FAIL   # exactly the planted size
H4 FAILED on the full sweep -- H1-H3 publication is BLOCKED       # exit 1
```
Seen red on **real** defects during the firing itself: pilot gate → pricing-basis
non-additivity (Rev 2.1, max err 2e-4); full-matrix gate → round(4) quantization below the
1e-6 tolerance (Rev 2.2: error distribution {0 x 626, exactly-1e-4 x 199}, raw in-process
identity 1.04e-17 at seed 1016; identity columns now round(10)). Tolerance never loosened.

## Part 3 — consumer-path probe with negative control

Probe: the consumer command (`feedback_sweep_stats.py`) recomputes every README/CHANGELOG
number from the artifact, exit 0. Negative control: same command against the effect-absent
state (artifact missing) → `FileNotFoundError`, exit 1.
`node rigor/scripts/check-effect-probe.mjs <records>` → `effect-probe: clean`.

## Gates at close (spec §10)

Full suite 202 passed under pins (incl. byte-identity + column-identity); sphinx `-W` build
succeeded; version bumped 0.3.0 (pins unchanged); every headline carries the planted-timing
label; distributions only, no single-seed quotation. Publish = the operator's commit of
artifact + docs (the atomic promotion step). Post-release note: run `pip install -e ".[dev]"`
to refresh the stale editable-install metadata (spike finding, 2026-07-18).
