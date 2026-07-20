---
ts: 2026-07-20T18:53:45Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: verified
---

**fact:** The local editable install still reports **0.1.0** while
`pyproject.toml` is at 0.3.0 — two minor versions behind. Anything reading
`importlib.metadata.version("closed-loop-default-detection")` (or
`cldd.__version__` via its metadata fallback) gets a wrong answer on this
machine. Harmless for the test suite, misleading for a release probe: do not
use it to confirm what 0.3.0 ships.

**basis:**

```
$ .venv/Scripts/python.exe -c "import importlib.metadata as m; print(m.version('closed-loop-default-detection'))"
  0.1.0
$ grep -n '^version' pyproject.toml   ->   7:version = "0.3.0"
$ grep -n '^version' CITATION.cff     ->   14:version: 0.2.0     # correct: flips at release
```

`CITATION.cff` at 0.2.0 is **not** a discrepancy — this repo's release pattern
holds it at the published version until the tag goes out.

**Fix:** `pip install -e ".[dev]"` as part of the 0.3.0 release steps.

**re-verify:** `.venv/Scripts/python.exe -c "import importlib.metadata as m; print(m.version('closed-loop-default-detection'))"`
