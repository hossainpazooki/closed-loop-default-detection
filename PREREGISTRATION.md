# Pre-registrations

A pre-registration here is a specification fixed before its experiment is run.
The specification is held privately. This file publishes its SHA-256 digest in a
dated commit, so that if the specification is released anyone can check it is
the document that existed before the data. Until then the digest proves a
document existed at that date, and nothing about what it says.

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
| Text | held outside this repository; not released |

The hypotheses, floors and reading rules are in the specification. The analysis
script is public and states them in its docstring; the specification adds the
decision record and the disclosure of what had been seen on already-spent seeds
before the hypotheses were worded.

## Segmented selection at strength 0 (Option C)

| | |
|---|---|
| Registered | 2026-11-03, by the commit that adds this entry |
| Specification | `2026-11-03-cldd-option-c-segmented-selection-design.md` |
| SHA-256 | `bb01ebf82014ace404c634c5f5ae882e55789b6fa6e3ea1a11379236e6a8ad76` |
| Judged by | `scripts/segment_stats.py` at the commit that adds this entry |
| Run by | `scripts/run_segment_sweep.py` at the commit that adds this entry |
| Seeds | `{1000 + 16i, i = 0..24}` at confounder strength 0: the v4 surface's strength-0 seeds, reused on purpose so the legacy cell must reproduce the surface's rows byte for byte; the policy cells have never run on them |
| Runs | 400 loop runs: 16 policy cells, two worlds, 25 seeds, one strength |
| State at registration | pilot gate passed on seed 1000 (round counts and timings read, no metric values); `artifacts/segment_frontier.csv` does not exist |
| Text | held outside this repository; not released |
| Run | 2026-11-03: the registering commit `7b735da` reached `origin/master` at 13:54:55Z; `artifacts/segment_frontier.csv` was created at 13:58:37Z; 400 of 400 runs, I-C1 green |
| Changed after the data were seen | the floor comparison in `scripts/segment_stats.py` (and `scripts/surface_stats.py`) tolerates 10⁻⁹ of IEEE noise on grid-step differences. The registered rule, one severity step, is unchanged; the change can only turn a "not confirmed" into a confirmation; disclosed in the README |

Four confirmatory hypotheses (losing overlap in an observable costs calibration
at severity 0, and moves the frontier; each in both worlds), one placebo
contrast in the flat world, and a falsification statement: the overlap-wall
explanation is stated as measured only if both frontier hypotheses are
confirmed. The analysis script states them in its docstring.
