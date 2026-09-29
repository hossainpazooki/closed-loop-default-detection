# Pre-registrations

A pre-registration here is a specification fixed before its experiment is run.
The specification is held privately. This file publishes its SHA-256 digest in a
dated commit, so that when the specification is released anyone can check it is
the document that existed before the data.

Digests are taken over LF-normalized bytes, the same convention as
`artifacts/SHA256SUMS.json`.

```bash
python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read().replace(b'\r\n',b'\n')).hexdigest())" <spec file>
```

## Strength-1.0 replication

| | |
|---|---|
| Registered | 2026-09-29, by the commit that adds this entry |
| Specification | `2026-09-29-cldd-strength-1.0-replication-design.md` |
| SHA-256 | `e2929493b3ea6ba0d6563f34bcc847bb8d61d66d4745606f8e8ab4abd119459d` |
| Judged by | `scripts/strength_replication_stats.py` at `f223b15` |
| Run by | `scripts/run_strength_replication.py` at `f223b15` |
| Seeds | `{5000 + 16i, i = 0..24}`, none of which any committed artifact has consumed |
| Runs | 300 loop runs: six confounder strengths, two worlds, 25 seeds |
| State at registration | no fresh seed run; `artifacts/strength_replication_frontier.csv` does not exist |

The hypotheses, floors and reading rules are in the specification. The analysis
script is public and states them in its docstring; the specification adds the
decision record and the disclosure of what had been seen on already-spent seeds
before the hypotheses were worded.
