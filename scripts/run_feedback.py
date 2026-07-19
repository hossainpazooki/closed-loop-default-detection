"""Model-in-the-loop feedback simulation: the loop the static harness never closed.

    python scripts/run_feedback.py [--quick]

From generation 1 onward the deployed model funds exactly the approval-rate
fraction it scores safest; only funded outcomes are observed; the next model
trains on them. Sweeps severity {0.4, 1.0} x exploration {0, 0.05} x seeds
{7, 42, 2026}, 6 generations each (generator="scm"), and writes every
generation to ``artifacts/feedback_generations.csv``.

What to look at:

* ``funded_default_rate`` (observable) vs ``declined_base_rate`` /
  ``declined_mean_pd`` (planted truth): the funded book can look *better* than
  generation 0 while the model's blind-spot under-prediction persists.
* ``diag_*`` columns: the observable positivity flag fires from generation 1 —
  a deterministic model policy destroys overlap by construction.
* exploration 0 vs 0.05: whether a small random-approval budget stabilizes the
  blind-spot bias across generations.

ASCII-only output (Windows console).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from cldd import FeedbackLoop, config  # noqa: E402

SEVERITIES = [0.4, 1.0]
EPS_GRID = [0.0, 0.05]
SEEDS = [7, 42, 2026]
N_GENERATIONS = 6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="seed 42, severity 0.4 only (smoke)")
    args = ap.parse_args()
    seeds = [42] if args.quick else SEEDS
    severities = [0.4] if args.quick else SEVERITIES

    rows = []
    for seed in seeds:
        for sev in severities:
            for eps in EPS_GRID:
                print(f"running seed={seed} severity={sev} eps={eps} ...", flush=True)
                res = FeedbackLoop(
                    selection_severity=sev,
                    n_generations=N_GENERATIONS,
                    exploration_rate=eps,
                    generator="scm",
                    seed=seed,
                ).run()
                for g in res.generations:
                    m, d = g.metrics, g.diagnostics
                    rows.append(
                        {
                            "seed": seed,
                            "selection_severity": sev,
                            "exploration_rate": eps,
                            "generation": g.generation,
                            "policy": g.policy,
                            "funded_rate": round(g.funded_rate, 4),
                            "funded_default_rate": round(g.funded_default_rate, 4),
                            "declined_ece": round(m.declined_ece, 4),
                            "declined_mean_pd": round(m.declined_mean_pd, 4),
                            "declined_base_rate": round(m.declined_base_rate, 4),
                            "all_ece": round(m.all_ece, 4),
                            "diag_propensity_auc": round(d.propensity_auc, 4),
                            "diag_ess_ratio": round(d.ess_ratio, 4),
                            "diag_below_floor": round(d.unfunded_below_floor, 4),
                            "diag_flagged": d.flagged,
                            "n_explored": g.n_explored,
                            "explored_defaults": g.explored_defaults,
                            # v3 additive columns (spec section 6): appended after
                            # the 17 v1 columns above, which stay untouched in
                            # name, order, and rounding -- the integration-stage
                            # column-identity gate depends on that.
                            "book_profit": None if g.book_profit is None else round(g.book_profit, 4),
                            "explored_profit": (
                                None if g.explored_profit is None else round(g.explored_profit, 4)
                            ),
                            "declined_empc": None if m.declined_empc is None else round(m.declined_empc, 4),
                            "declined_emp_h": (
                                None if m.declined_emp_h is None else round(m.declined_emp_h, 4)
                            ),
                        }
                    )

    df = pd.DataFrame(rows)
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.ARTIFACTS_DIR / "feedback_generations.csv"
    df.to_csv(out, index=False)
    print(f"\nwrote {out}  ({len(df)} rows)")

    # Summary: mean blind-spot under-prediction (true declined base rate minus
    # mean predicted PD) over the model-policy generations (1+).
    model_gens = df[df["policy"] == "model"].copy()
    model_gens["under_prediction"] = (
        model_gens["declined_base_rate"] - model_gens["declined_mean_pd"]
    )
    print("\nmean blind-spot under-prediction, model generations (truth minus predicted):")
    for sev in severities:
        for eps in EPS_GRID:
            d = model_gens[
                (model_gens["selection_severity"] == sev)
                & (model_gens["exploration_rate"] == eps)
            ]
            print(
                f"  severity {sev} eps={eps}: {d['under_prediction'].mean():+.4f} "
                f"(declined ECE mean {d['declined_ece'].mean():.4f}; "
                f"diag flagged {int(d['diag_flagged'].sum())}/{len(d)} generations)"
            )


if __name__ == "__main__":
    main()
