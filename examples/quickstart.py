"""Quickstart: run the closed loop, then add a correction lever by hand.

Synthetic-only (no real data). Two parts:

1. CLASSIC PATH -- drive ``SelectiveLabelsLoop(improve_mode="both")`` and print
   the operating frontier plus a per-round (severity, naive declined ECE, passed)
   table. This is the API that 13 call sites already use; it is unchanged.

2. PLUGGABLE PATH -- the loop now accepts ``correctors=[...]``. A correction
   lever is just a ``Corrector`` subclass (name, control_priority, apply). We
   define a one-off ``NaiveCopyCorrector`` -- it returns the SAME metrics as the
   built-in naive lever but with a HIGHER ``control_priority``, so the loop's
   control_metric is driven by it instead. That is the whole extension surface:
   adding a lever is adding a class.

Run it::

    .venv/Scripts/python.exe examples/quickstart.py

All stdout is ASCII (Windows cp1252 safe). Runtime is kept modest with a small
cohort and few rounds; the numbers here are illustrative, not the headline
frontier from the full configuration.
"""

from __future__ import annotations

from cldd.correctors import (
    CorrectionOutcome,
    Corrector,
    CorrectorContext,
    NaiveCorrector,
    IPWReweightCorrector,
    DisjointRetrainCorrector,
)
from cldd.loop import SelectiveLabelsLoop

# Small cohort / few rounds so the script finishes quickly. The classic full
# configuration uses larger defaults; see config.py.
N_APPLICANTS = 1500
MAX_ROUNDS = 3


def _fmt_passed(passed: bool) -> str:
    return "yes" if passed else "no"


def run_classic() -> None:
    """Part 1: the classic improve_mode API, unchanged."""
    print("=" * 64)
    print("PART 1 -- classic path: SelectiveLabelsLoop(improve_mode='both')")
    print("=" * 64)

    loop = SelectiveLabelsLoop(
        improve_mode="both",
        n_applicants=N_APPLICANTS,
        max_rounds=MAX_ROUNDS,
    )
    result = loop.run()

    if result.frontier_severity is None:
        print("operating frontier: none (correction never cleared the target)")
    else:
        print("operating frontier (highest passing severity): "
              "%.4f" % result.frontier_severity)
    print("target declined ECE: %.4f" % result.target_declined_ece)
    print()

    header = "%-10s %-20s %-8s" % ("severity", "naive declined ECE", "passed")
    print(header)
    print("-" * len(header))
    for r in result.rounds:
        print("%-10.4f %-20.6f %-8s" % (
            r.selection_severity,
            r.naive.declined_ece,
            _fmt_passed(r.passed),
        ))
    print()


class NaiveCopyCorrector(Corrector):
    """Demo lever: same metrics as the naive lever, higher control priority.

    This is the entire contract for adding a correction lever:

    * a ``name`` (key under which its metrics land in ``RoundResult.corrections``),
    * a ``control_priority`` (the present corrector with the highest priority
      drives ``control_metric``; ties resolve to first-in-list),
    * an ``apply(cohort, ctx)`` that returns a ``CorrectionOutcome``.

    We delegate the actual computation to the built-in ``NaiveCorrector`` so the
    numbers are identical -- the only thing we change is who wins control. The
    built-in naive lever has control_priority=0; anything above that outranks it.
    """

    name = "naive_copy"
    control_priority = 99  # outranks every built-in lever

    def __init__(self) -> None:
        self._delegate = NaiveCorrector()

    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        return self._delegate.apply(cohort, ctx)


def run_pluggable() -> None:
    """Part 2: the new correctors=[...] path with a custom lever."""
    print("=" * 64)
    print("PART 2 -- pluggable path: SelectiveLabelsLoop(correctors=[...])")
    print("=" * 64)

    # Build the lever list explicitly. Our NaiveCopyCorrector has the highest
    # control_priority, so it -- not the built-in naive lever -- drives the loop's
    # control_metric, even though its metrics are byte-identical to naive.
    correctors = [
        NaiveCorrector(),
        IPWReweightCorrector(),
        DisjointRetrainCorrector(),
        NaiveCopyCorrector(),
    ]
    loop = SelectiveLabelsLoop(
        correctors=correctors,
        n_applicants=N_APPLICANTS,
        max_rounds=MAX_ROUNDS,
    )
    result = loop.run()

    print("levers in play: " + ", ".join(c.name for c in correctors))
    print("control is driven by the highest control_priority lever present "
          "(here: naive_copy)")
    print()

    header = "%-10s %-22s %-22s %-8s" % (
        "severity", "naive declined ECE", "control_metric", "passed",
    )
    print(header)
    print("-" * len(header))
    for r in result.rounds:
        # corrections is the general name->LeverMetrics map the new field exposes.
        naive_ece = r.corrections["naive"].declined_ece
        copy_ece = r.corrections["naive_copy"].declined_ece
        # control_metric equals the naive_copy declined ECE (highest priority),
        # which equals the naive declined ECE because the metrics are identical.
        print("%-10.4f %-22.6f %-22.6f %-8s" % (
            r.selection_severity,
            naive_ece,
            r.control_metric,
            _fmt_passed(r.passed),
        ))

        assert copy_ece == naive_ece, "naive_copy must mirror naive metrics"
        assert r.control_metric == copy_ece, "control must follow highest priority"
    print()
    print("note: control_metric tracks naive_copy (priority 99), and because the "
          "demo")
    print("lever just mirrors naive, control_metric == naive declined ECE above.")


def main() -> int:
    run_classic()
    run_pluggable()
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
