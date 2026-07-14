"""Central configuration: paths, seeds, loan economics, and the frontier grid.

Everything here is either a *fact* (loan terms, the SMB challenge's ~17% base
default rate) or a single-source-of-truth knob for the closed loop. Per-model
hyperparameters live in the individual modules so this file stays scannable.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parents[2]  # repo root
ARTIFACTS_DIR = ROOT / "artifacts"          # gitignored; frontier CSV + plots

# --------------------------------------------------------------------------- #
# Reproducibility
# --------------------------------------------------------------------------- #

RANDOM_SEED = 42

# Disjoint train-cohort offset for the retrain lever. Large enough that train
# seeds (RANDOM_SEED + TRAIN_SEED_OFFSET + iteration) never collide with measure
# seeds (RANDOM_SEED + iteration).
TRAIN_SEED_OFFSET = 1000

# --------------------------------------------------------------------------- #
# Synthetic SMB loan economics + portfolio shape (mirrors the challenge brief)
# --------------------------------------------------------------------------- #

TERM_DAYS = 60                  # daily ACH draws over a 60-day term
APR = 0.35                      # annualized
ORIGINATION_FEE_RATE = 0.03     # 3% of amount, collected up front

TARGET_BASE_DEFAULT_RATE = 0.17  # the challenge's labeled pool ran ~17.4%
DEFAULT_APPROVAL_RATE = 0.60     # fraction of applicants the prior policy funds

# Decision threshold on PD used only for the *detection F1* diagnostic
# (approve/decline economics are out of scope for this harness).
POLICY_PD_THRESHOLD = 0.5

# --------------------------------------------------------------------------- #
# Closed-loop frontier search over selection severity
# --------------------------------------------------------------------------- #

START_SEVERITY = 0.0    # severity 0 == approval independent of true risk (MAR)
SEVERITY_STEP = 0.2
MAX_SEVERITY = 1.0      # severity 1 == approval tracks full latent risk
MAX_ROUNDS = 8

# A round "passes" when the corrected declined-subpopulation calibration error
# (ECE) stays at or below this. Lower is better; the frontier is the highest
# severity still passing.
TARGET_DECLINED_ECE = 0.10

DEFAULT_N_APPLICANTS = 4000

# --------------------------------------------------------------------------- #
# EMP reporting layer (cldd.emp) — v2 measurement axis, never loop control
# --------------------------------------------------------------------------- #
# Literature EMPC prior. Verified against the primary source before entry
# (2026-07-13 spike): Verbraken, Bravo, Weber & Baesens (2014), EJOR
# 238(2):505-513 — h(lambda) = p0*delta(0) + p1*delta(1) + (1-p0-p1)*U(0,1),
# constant ROI, computed over the ROC convex hull (paper Eqs. 13/15). The
# defaults are the benchmark-standard CRAN EMP::empCreditScoring values, so
# empc columns are comparable to the published literature.
EMPC_P0 = 0.55       # P(lambda = 0): full recovery
EMPC_P1 = 0.10       # P(lambda = 1): total loss
EMPC_ROI = 0.2644    # per-loan return on investment, fraction of principal

# --------------------------------------------------------------------------- #
# Observable positivity-diagnostic thresholds (cldd.diagnostics)
# --------------------------------------------------------------------------- #
# Calibrated on this harness's severity grids (flat + SCM, seeds {7, 42, 2026},
# n=4000): each component individually separates every pass-severity cell
# (<= 0.4) from every fail-severity cell (>= 0.6) in all 6 grid runs —
# pass-side worst cases AUC 0.831 / ESS 0.915 / floor 0.0025 vs fail-side worst
# cases 0.877 / 0.844 / 0.020. The flag detects the positivity-breakdown
# REGIME, not per-cohort ECE (one flat seed missed the 0.10 ECE target at
# severity 0.4 with healthy diagnostics). A *proposal* for real-data
# monitoring, validated only in the two synthetic worlds.
DIAG_PROPENSITY_AUC_MAX = 0.85
DIAG_ESS_RATIO_MIN = 0.875
DIAG_UNFUNDED_BELOW_FLOOR_MAX = 0.01

# Exploration lever: dedicated RNG stream tags so the explore draw can never
# collide with (or shift) a generator's PCG64 stream or another lever's draw.
EXPLORE_STREAM_LOOP = 7919
EXPLORE_STREAM_FEEDBACK = 104729

# --------------------------------------------------------------------------- #
# Reject-inference correctors (cldd.reject_inference)
# --------------------------------------------------------------------------- #
# RI levers are graded against planted truth on a HELD-OUT fold of the declined
# population (the "recovery of this declined population's labels" claim). The
# pseudo-label fold and the parcelling label draw get dedicated RNG stream tags,
# same discipline as the exploration lever, so they can never shift a generator's
# PCG64 stream or another lever's draw.
RI_EVAL_FRACTION = 0.5        # fraction of declines held out for grading
RI_SCORE_BANDS = 10           # quantile score bands for augmentation / parcelling
RI_PARCEL_FACTOR = 1.5        # parcelling: bad-rate uplift over the accepted band rate
RI_SPLIT_STREAM = 15485863    # declined train/eval split
RI_PARCEL_STREAM = 32452843   # parcelling pseudo-label draw
