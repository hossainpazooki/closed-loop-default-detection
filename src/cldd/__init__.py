"""Closed-loop default-rate detection — a CLUE-style harness for selective labels.

generate (``synthetic``) -> measure (``eval_default``) -> improve/frontier
(``loop``). See README.md for the CLUE mapping and how to run.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:  # pyproject `version` is the single source of truth (read from installed metadata)
    __version__ = _pkg_version("closed-loop-default-detection")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0.1.0"

from .correctors import (
    CorrectionOutcome,
    Corrector,
    CorrectorContext,
    DisjointRetrainCorrector,
    ExplorationCorrector,
    IPWReweightCorrector,
    NaiveCorrector,
)
from .counterfactual import (
    CounterfactualResult,
    GComputationEstimator,
    generate_queries,
    run_counterfactual_eval,
)
from .diagnostics import PositivityDiagnostics, positivity_diagnostics
from .reject_inference import (
    AugmentationCorrector,
    FuzzyAugmentationCorrector,
    ParcellingCorrector,
    ReclassificationCorrector,
    RejectInferenceCorrector,
)
from .eval_default import PdDetectionResult, fit_observed_model, score_pd_detection
from .model_pd import CalibratedPDClassifier, CalibratedPDModel
from .feedback import FeedbackLoop, FeedbackResult, GenerationResult
from .loop import LeverMetrics, LoopResult, RoundResult, SelectiveLabelsLoop
from .scm import (
    BANK_FEED_COLUMNS,
    FEATURE_COLUMNS,
    INTERVENABLE_FEATURES,
    InterventionResult,
    SCMState,
    StructuralBorrowerGenerator,
    dag_children,
    dag_parents,
)
from .synthetic import SyntheticBorrowerGenerator

__all__ = [
    "__version__",
    "SyntheticBorrowerGenerator",
    "StructuralBorrowerGenerator",
    "SCMState",
    "InterventionResult",
    "INTERVENABLE_FEATURES",
    "FEATURE_COLUMNS",
    "BANK_FEED_COLUMNS",
    "dag_children",
    "dag_parents",
    "SelectiveLabelsLoop",
    "LoopResult",
    "RoundResult",
    "LeverMetrics",
    "Corrector",
    "CorrectorContext",
    "CorrectionOutcome",
    "NaiveCorrector",
    "IPWReweightCorrector",
    "DisjointRetrainCorrector",
    "ExplorationCorrector",
    "RejectInferenceCorrector",
    "ReclassificationCorrector",
    "AugmentationCorrector",
    "FuzzyAugmentationCorrector",
    "ParcellingCorrector",
    "FeedbackLoop",
    "FeedbackResult",
    "GenerationResult",
    "PositivityDiagnostics",
    "positivity_diagnostics",
    "PdDetectionResult",
    "fit_observed_model",
    "score_pd_detection",
    "CalibratedPDModel",
    "CalibratedPDClassifier",
    "CounterfactualResult",
    "GComputationEstimator",
    "run_counterfactual_eval",
    "generate_queries",
]
