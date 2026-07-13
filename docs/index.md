# closed-loop-default-detection

A self-contained research harness that stress-tests **probability-of-default (PD)**
modeling under **selective labels** and reports the model's honest **operating
frontier** — the highest selection severity at which calibration on the *declined*
subpopulation still holds.

The [README](https://github.com/hossainpazooki/closed-loop-default-detection#readme)
is the short, results-first tour; this site carries the full documentation. The
accompanying article — the independent results-and-methodology assessment — is
[`FABLE.md`](https://github.com/hossainpazooki/closed-loop-default-detection/blob/master/FABLE.md).

```{toctree}
:maxdepth: 2
:caption: Contents

quickstart
how-it-works
configuration
validation
api
reject_inference
```

## Install

```bash
pip install closed-loop-default-detection    # from PyPI; import name is `cldd`
```

For development (tests, docs, the committed evidence), install from source:

```bash
pip install -e ".[dev]"     # editable install + pytest
```

The library declares dependency *ranges*; the exact provenance pins under which the
committed numbers were captured live in `requirements-dev.txt`.

## Indices

- {ref}`genindex`
- {ref}`modindex`
