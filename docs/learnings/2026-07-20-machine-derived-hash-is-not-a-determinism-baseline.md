---
ts: 2026-07-20T18:53:54Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: verified
---

**fact:** A sha256 literal derived on one machine is not a determinism baseline —
it encodes that machine's floats. `test_default_path_byte_identity_regression`
pinned a hash computed on the author's Windows box; HistGBT floats shift across
OS *and* numpy version, so the constant failed 14/15 CI jobs while passing
locally. The failure was structural, not flaky: `pinned-repro` runs on
`ubuntu-latest`, so a Windows-derived constant could never pass there.

**basis:** Two jobs in the red run on `f2f1123` resolved *identical* dependency
versions (numpy 2.4.6 + scikit-learn 1.9.0, exactly `requirements-dev.txt`) and
disagreed purely by OS:

```
$ rid=$(gh run list --limit 10 --json databaseId,headSha,workflowName \
    --jq '.[] | select(.headSha|startswith("f2f1123")) | select(.workflowName=="CI") | .databaseId')
$ for j in "py3.11 / ubuntu-latest" "py3.11 / windows-latest"; do ... done
  py3.11 / ubuntu-latest -> failure
  py3.11 / windows-latest -> success
```

`py3.11/windows-latest` was the single green compat job in that run. Jobs on
numpy 2.5.1 failed on every OS, so the hash moved with numpy version too.

**Fix that replaced it:** measure the identity *differentially* — reconstruct
`feedback.py` from git blob `da81c98`, load it as `cldd._prev3_feedback`, and
compare both runs in the same process. Platform-invariant by construction, so it
correctly needs no `pinned` marker.

**re-verify:** `gh run view $(gh run list --limit 10 --json databaseId,headSha,workflowName --jq '.[] | select(.headSha|startswith("f2f1123")) | select(.workflowName=="CI") | .databaseId') --json jobs --jq '.jobs[] | select(.name|test("py3.11")) | "\(.name): \(.conclusion)"'`
