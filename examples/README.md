# Examples

Runnable, synthetic-only demonstrations of the `cldd` API. No real data is
required or used.

## `quickstart.py`

A single script in two parts:

1. **Classic path** — runs `SelectiveLabelsLoop(improve_mode="both").run()` and
   prints the detector's **operating frontier** (the highest selection severity
   at which correction still cleared the target declined-cohort ECE) plus a
   per-round table of `(severity, naive declined ECE, passed)`.

2. **Pluggable path** — shows that a correction lever is now just a class. It
   defines a tiny `NaiveCopyCorrector` (a `Corrector` subclass with `name`,
   `control_priority`, and `apply`), passes it via
   `SelectiveLabelsLoop(correctors=[...])`, and demonstrates that because the
   custom lever has the highest `control_priority`, it drives the loop's
   `control_metric`. Its metrics mirror the built-in naive lever, so the demo
   also asserts byte-equality between the two — adding a lever changes *who
   controls the loop*, not the underlying numbers.

The cohort size and round count are kept small (`n_applicants=1500`,
`max_rounds=3`) so the script finishes quickly; the printed numbers are
illustrative, not the headline frontier from the full configuration.

### Run it

From the repo root, using the project virtualenv:

```bash
.venv/Scripts/python.exe examples/quickstart.py
```

The script exits `0` on success. All output is ASCII (safe for the Windows
cp1252 console).
