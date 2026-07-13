# Tests, validation, and reproducibility

```bash
pytest                          # full suite (run under the pinned environment for the float-exact tests)
pytest -m "not pinned"          # the subset the CI compat matrix runs off-pins
pytest --cov=cldd --cov-report=term-missing   # coverage of the public (synthetic-only) suite
```

Two project-specific validation gates beyond the unit tests:

```bash
# Marginal-fidelity gate — SCM cohort vs real-data marginals; exit 0 = pass, 1 = fail/data-missing
CLDD_DATA_DIR=/path/to/dataset python scripts/check_fidelity.py
python scripts/check_fidelity.py --data-dir /path/to/dataset   # equivalent, explicit flag

# Reproduce the headline statistic from committed evidence
python scripts/paired_significance.py   # recomputes from artifacts/seed_sweep_25.csv
```

## The marginal-fidelity gate

The gate validates **univariate marginals only** — base rate, feed rate, missingness,
per-feature p1/p50/p99, and categorical top-frequencies — so "fidelity PASSED" means *the
modeled marginals match the real data*, **not** that the generator is faithful in the
joint/causal distribution.

The real Intuit dataset is **private and not shipped**. Point the gate at your own copy
(a directory containing `train.csv`) via the portable `CLDD_DATA_DIR` environment variable
— e.g. `CLDD_DATA_DIR=/path/to/dataset python scripts/check_fidelity.py` — or the equivalent
`--data-dir` flag; with the data absent it raises a clear error naming `CLDD_DATA_DIR` (it is
**not** runnable on the synthetic-only quickstart). This is the **only** command that needs the
real `train.csv`; everything else, including the whole test suite, runs on synthetic data alone.

Because that dataset is private and absent on public CI, the fidelity gate's real-data path is
never exercised there — so **coverage of `cldd/fidelity.py`'s data-loading branch is low on CI
by design, not an oversight.** The `coverage (public suite)` CI job and the local
`pytest --cov=cldd` command both measure only the synthetic-only suite.

## Building the docs

The Sphinx API reference builds in the same strict mode Read the Docs uses:

```bash
pip install -e ".[docs]"
sphinx-build -b html -W docs docs/_build/html   # -W: warnings are errors
```

CI runs three gates: a `pinned-repro` job (full suite under the exact pins), a cross-version /
cross-OS `compat` matrix (`-m "not pinned"`), and a `docs` job (`sphinx-build -W`).

## Reproducibility and the pinned tests

`HistGradientBoosting` float output shifts across scikit-learn releases, so the committed
numbers and the frozen byte-identity baseline were captured under a **pinned** environment —
**scikit-learn 1.9.0 / numpy 2.4.6** (Python 3.14.2), recorded in `requirements-dev.txt`. To
reproduce those exact figures:

```bash
pip install -r requirements-dev.txt && pip install -e . --no-deps
```

The **six** float-sensitive tests are marked `pinned` and reproduce **only** under those pins;
the CI `compat` matrix deselects them with `-m "not pinned"`. The library deps stay as ranges
so a plain `pip install` works alongside your own sklearn.

The model stack is deliberately **scikit-learn-only** (`HistGradientBoostingClassifier` +
isotonic calibration) as a portability decision: the harness behaves identically in every
environment it runs in, with no compiled extras to install. LightGBM / XGBoost are a possible
future model tier, not a current dependency.

## Troubleshooting

- **`pytest` shows a few float-mismatch failures (byte-identity baseline, seed-robustness, or
  exploration thresholds).** You are on a different scikit-learn/numpy than the pins. Install
  the pinned versions (`pip install -r requirements-dev.txt`); under **scikit-learn 1.9.0 /
  numpy 2.4.6** the full suite passes (123 tests).
- **`ModuleNotFoundError: No module named 'cldd'` under `pytest`.** Install the package
  (`pip install -e ".[dev]"`); tests import `cldd` as an installed package.
- **`check_fidelity.py` exits 1 with "data not found".** The real dataset is private and not
  shipped — set `CLDD_DATA_DIR=/path/to/dataset` (or pass `--data-dir /path/to/dataset`), a
  directory containing `train.csv`. The gate is not runnable on the synthetic-only quickstart.
- **`run_seed_sweep.py` is slow / memory-heavy.** By design it launches one subprocess per
  (seed, severity) eval; use `--quick` for a seed-42 smoke run.
- **No plot window appears.** Scripts use the headless `Agg` backend and write PNGs to
  `artifacts/`; there is nothing to display interactively.
