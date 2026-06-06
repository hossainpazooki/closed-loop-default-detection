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
# seeds (RANDOM_SEED + iteration). This is the no-leakage discipline ported from
# upstream-label-correction/clue/loop.py.
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
