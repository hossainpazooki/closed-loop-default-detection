---
ts: 2026-07-20T18:54:21Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: refuted-assumption
---

**fact:** OpenMP thread count does **not** explain this repo's HistGBT float
drift. The obvious hypothesis for a hash that differs between machines —
`HistGradientBoosting` being bit-reproducible only at a fixed thread count — is
wrong here. Don't spend time on it again; the drift is OS/BLAS and numpy
version, per
[[2026-07-20-machine-derived-hash-is-not-a-determinism-baseline]].

**basis:** the v1-field hash of the canonical default-path run is stable across a
1x-to-8x thread sweep on one machine:

```
$ for n in 1 8; do OMP_NUM_THREADS=$n .venv/Scripts/python.exe -c "
    import sys; sys.path.insert(0,'tests')
    from cldd.feedback import FeedbackLoop
    from test_feedback_flags import _hash_v1_fields, RUN_KWARGS
    print('OMP_NUM_THREADS=$n ->', _hash_v1_fields(FeedbackLoop(**RUN_KWARGS).run())[:16])"; done
  OMP_NUM_THREADS=1 -> e8f0d3c4d1e338eb
  OMP_NUM_THREADS=8 -> e8f0d3c4d1e338eb
```

(An earlier capture in this session also covered 2 and 4 threads — same hash.)
Note `e8f0d3c4…` is exactly the historical pinned literal, so the differential
test reproduces the old baseline on the machine where that baseline was valid.

**re-verify:** `for n in 1 8; do OMP_NUM_THREADS=$n .venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); from cldd.feedback import FeedbackLoop; from test_feedback_flags import _hash_v1_fields, RUN_KWARGS; print(_hash_v1_fields(FeedbackLoop(**RUN_KWARGS).run())[:16])"; done`
