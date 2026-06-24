# closed-loop-default-detection

A self-contained research harness that stress-tests **probability-of-default (PD)**
modeling under **selective labels** and reports the model's honest **operating
frontier** — the highest selection severity at which calibration on the *declined*
subpopulation still holds.

This site is the API reference. For the narrative overview, the methodology
assessment, and how to run the drivers, see the project
[README](https://github.com/hossainpazooki/closed-loop-default-detection#readme).

```{toctree}
:maxdepth: 2
:caption: Contents

quickstart
api
reject_inference
```

## Install

```bash
pip install -e ".[dev]"     # editable install + pytest
```

The library declares dependency *ranges*; the exact provenance pins under which the
committed numbers were captured live in `requirements-dev.txt`.

## Indices

- {ref}`genindex`
- {ref}`modindex`
