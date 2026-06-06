"""Closed-loop default-rate detection — a CLUE-style harness for selective labels.

generate (``synthetic``) -> measure (``eval_default``) -> improve/frontier
(``loop``). See README.md for the CLUE mapping and how to run.
"""

from __future__ import annotations

from .eval_default import PdDetectionResult, fit_observed_model, score_pd_detection
from .loop import LeverMetrics, LoopResult, RoundResult, SelectiveLabelsLoop
from .synthetic import SyntheticBorrowerGenerator

__all__ = [
    "SyntheticBorrowerGenerator",
    "SelectiveLabelsLoop",
    "LoopResult",
    "RoundResult",
    "LeverMetrics",
    "PdDetectionResult",
    "fit_observed_model",
    "score_pd_detection",
]
