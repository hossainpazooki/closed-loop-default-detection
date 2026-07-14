# Configuration

**The only environment variable is `CLDD_DATA_DIR`** (the marginal-fidelity gate's real-data
location). Everything else is code-level and explicit; per-run options are CLI flags on the
drivers. `src/cldd/config.py` is the single source of truth:

| Constant | Default | Meaning |
|---|---|---|
| `RANDOM_SEED` | `42` | base seed for all streams |
| `TRAIN_SEED_OFFSET` | `1000` | disjoint-cohort offset for the no-leakage retrain lever |
| `START_SEVERITY` / `SEVERITY_STEP` / `MAX_SEVERITY` | `0.0` / `0.2` / `1.0` | the severity grid the loop sweeps |
| `MAX_ROUNDS` | `8` | frontier-search round cap |
| `TARGET_DECLINED_ECE` | `0.10` | a round passes when corrected declined ECE ≤ this |
| `DEFAULT_N_APPLICANTS` | `4000` | cohort size |
| `TARGET_BASE_DEFAULT_RATE` / `DEFAULT_APPROVAL_RATE` | `0.17` / `0.60` | planted base rate / prior-policy funding rate |
| `TERM_DAYS` / `APR` / `ORIGINATION_FEE_RATE` | `60` / `0.35` / `0.03` | loan economics of the synthetic daily-ACH term loan |
| `POLICY_PD_THRESHOLD` | `0.5` | PD cutoff used **only** for the detection-F1 diagnostic (approve/decline economics are out of scope) |
| `EMPC_P0` / `EMPC_P1` / `EMPC_ROI` | `0.55` / `0.10` / `0.2644` | literature EMPC prior (Verbraken et al. 2014): P(λ=0), P(λ=1), and the constant ROI. Source-verified; the CRAN `EMP::empCreditScoring` defaults, so `empc` stays benchmark-comparable. **Not** this harness's own economics — see the [README](https://github.com/hossainpazooki/closed-loop-default-detection#pricing-the-frontier-v2) on why they disagree |
| `EXPLORE_STREAM_LOOP` / `EXPLORE_STREAM_FEEDBACK` | — | dedicated RNG stream tags so the exploration draw can never shift a generator's stream |
| `RI_*` | — | reject-inference knobs: held-out eval fraction, score bands, parcelling uplift, RNG streams |
| `DIAG_*` | — | positivity-diagnostic thresholds (see the calibration note in `config.py`) |

The marginal-fidelity gate's real-data location is portable: set the **`CLDD_DATA_DIR`**
environment variable to a directory containing `train.csv` (e.g.
`CLDD_DATA_DIR=/path/to/dataset python scripts/check_fidelity.py`), or pass the equivalent
`--data-dir /path/to/dataset` flag. The real Intuit dataset is private and not shipped, so
with the data absent the gate raises a clear error naming `CLDD_DATA_DIR` rather than falling
back to a machine-specific path.
