"""VERIFY FIDELITY gate runner.

Builds a StructuralBorrowerGenerator cohort, compares its marginals against the
real Intuit dataset, prints the report table, and exits non-zero if the gate
fails. Run from anywhere::

    python scripts/check_fidelity.py
    python scripts/check_fidelity.py --data-dir /path/to/dataset --n 16000

Exit code 0 == gate passed, 1 == gate failed (or data not found).

When ``--data-dir`` is omitted, the ``CLDD_DATA_DIR`` env var is honored as the
default dataset location (via ``DEFAULT_DATA_DIR``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make ``cldd`` importable when run as a loose script (src/ layout).
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from cldd.fidelity import DEFAULT_DATA_DIR, run_fidelity_gate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Verify SCM *marginal* fidelity vs real data (univariate "
                    "marginals only; does not check the joint distribution).")
    p.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR),
                   help="real dataset directory (contains train.csv).")
    p.add_argument("--split", default="train", help="real split to compare against.")
    p.add_argument("--n", type=int, default=12000,
                   help="synthetic cohort size (>=8000 recommended for stable quantiles).")
    p.add_argument("--seed", type=int, default=42, help="generator seed.")
    p.add_argument("--strict-categoricals", action="store_true",
                   help="count categorical top-frequency checks toward the verdict.")
    args = p.parse_args(argv)

    try:
        report = run_fidelity_gate(
            data_dir=args.data_dir,
            split=args.split,
            n_applicants=args.n,
            seed=args.seed,
            strict_categoricals=args.strict_categoricals,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(report.to_table())
    if not report.passed:
        print("\nMARGINAL FIDELITY GATE FAILED.", file=sys.stderr)
        return 1
    print("\nMARGINAL FIDELITY GATE PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
