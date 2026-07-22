---
ts: 2026-07-22T17:36:56Z
commit: 1ab178b
session: 7eb7bd13-dbfd-4bce-bc15-cd0e01c8827a
status: verified
---

**fact:** The author email was dropped from `pyproject.toml` and `CITATION.cff`
at 0.3.0 (`1ab178b`), and the published 0.3.0 metadata is clean — but 0.1.0 and
0.2.0 on PyPI carry it **permanently**: published release files and their
metadata are immutable, and mirrors (bandersnatch, deps.dev, libraries.io) have
already scraped them. Deleting the old releases or the whole project was
assessed and **rejected**: deletion doesn't reach the mirrors, burns the exact
filenames forever (PyPI never allows re-upload of a used filename), and
project deletion would free the name and destroy the trusted-publisher
registration. Metadata scrubbing on PyPI is forward-only.

**basis:** Captured 2026-07-22T17:36:56Z at `1ab178b`:

```
$ curl -s https://pypi.org/pypi/closed-loop-default-detection/0.2.0/json
  0.2.0 author_email: 'Hossain Pazooki <hossain@pazooki.com>'   # immutable
$ curl -s https://pypi.org/pypi/closed-loop-default-detection/0.3.0/json
  0.3.0 author_email: None                                       # clean
```

Wheel-level check pre-publish: 0.3.0 METADATA carries `Author: Hossain Pazooki`
with no `Author-email` line.

**re-verify:** `curl -s https://pypi.org/pypi/closed-loop-default-detection/0.3.0/json | python -c "import json,sys;print(json.load(sys.stdin)['info']['author_email'])"` (expect `None`)
