# Quickstart

Everything below runs on synthetic data — no real dataset is required.

## Run the closed loop

```python
from cldd import SelectiveLabelsLoop

loop = SelectiveLabelsLoop(improve_mode="both")   # "reweight" | "retrain" | "both"
result = loop.run()

print("Operating frontier (highest passing severity):", result.frontier_severity)
for r in result.rounds:
    print(r.selection_severity, r.naive.declined_ece, r.passed)
```

`result` is a {class}`~cldd.loop.LoopResult`; each entry of `result.rounds` is a
{class}`~cldd.loop.RoundResult` carrying the per-lever
{class}`~cldd.correctors.LeverMetrics` and the `control_metric` that drives the
frontier search.

## Add a correction lever

The correction levers are **pluggable**. Pass `correctors=[...]` instead of
`improve_mode`; a lever is a {class}`~cldd.correctors.Corrector` subclass with a
`name`, a `control_priority`, and an `apply` method. The applied lever with the
highest `control_priority` drives loop control (built-ins: `naive=0`, `retrain=1`,
`reweight=2`, `explore=3`).

```python
from cldd import SelectiveLabelsLoop, Corrector, NaiveCorrector, CorrectionOutcome

class MyCorrector(Corrector):
    name = "my_lever"
    control_priority = 5
    def apply(self, cohort, ctx) -> CorrectionOutcome:
        ...   # return CorrectionOutcome(metrics=..., info={})

result = SelectiveLabelsLoop(correctors=[NaiveCorrector(), MyCorrector()]).run()
```

When `correctors` is omitted the loop builds the default list from `improve_mode` /
`exploration_rate` exactly as before, so the legacy API is unchanged. See
`examples/quickstart.py` in the repository for a runnable end-to-end demo, and
`CONTRIBUTING.md` for the full corrector contract.

## Score synthetic-vs-real fidelity

{class}`~cldd.fidelity.FidelityReport` exposes an SDMetrics-style summary:

```python
from cldd.fidelity import run_fidelity_gate

report = run_fidelity_gate(data_dir="/path/to/dataset")  # needs the real train.csv
print(report.get_score())     # 0..1 fraction of counting checks that passed
report.get_details()          # per-check pandas DataFrame
```
