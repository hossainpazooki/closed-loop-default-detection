---
ts: 2026-07-22T17:36:49Z
commit: 1ab178b
session: 7eb7bd13-dbfd-4bce-bc15-cd0e01c8827a
status: verified
---

**fact:** Minutes after the `v0.3.0` tag published, PyPI's **project-level JSON
endpoint** (`/pypi/<name>/json`) still served `latest: 0.2.0` while the **simple
index** (`/simple/<name>/`, what pip actually resolves against) and the
**version-specific endpoint** (`/pypi/<name>/0.3.0/json`) already served 0.3.0
— CDN (Fastly) cache lag. A release-effect probe that reads only the project
JSON can falsely report the release absent; conversely, during the lag window
it still shows the *previous* version's metadata (here: the author email 0.3.0
removed).

**basis:** Captured earlier this session at `1ab178b` (tag `v0.3.0` pushed,
pre-17:36Z):

```
$ curl -s https://pypi.org/pypi/closed-loop-default-detection/json
  latest: 0.2.0 | releases: ['0.1.0', '0.2.0']          # stale
$ curl -s .../simple/closed-loop-default-detection/  (application/vnd.pypi.simple.v1+json)
  simple index versions: ['0.1.0', '0.2.0', '0.3.0']    # fresh
$ fresh venv: pip install closed-loop-default-detection
  installed version: 0.3.0                               # consumer path fresh
```

Lag confirmed cleared at 2026-07-22T17:36:49Z: the same project-JSON probe then
returned `latest: 0.3.0`. The lag itself is transient and not reproducible on
demand — what is re-verifiable is the probe *method*.

**Rule:** verify a release against the simple index or a clean `pip install`,
never the project-level JSON alone.

**re-verify:** `curl -s -H "Accept: application/vnd.pypi.simple.v1+json" https://pypi.org/simple/closed-loop-default-detection/ | python -c "import json,sys;print(json.load(sys.stdin)['versions'])"`
