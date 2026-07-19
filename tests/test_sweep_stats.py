"""Tests for scripts/feedback_sweep_stats.py (spec section 7 bullet 4).

Hand-built fixtures with known signs, known Holm ordering, known floor
arithmetic, and a known H4 consistency/inconsistency pair -- no dependence on
the real 450-run sweep, so these run standalone and fast.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location(
    "feedback_sweep_stats", SCRIPTS_DIR / "feedback_sweep_stats.py"
)
fss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fss)


# --------------------------------------------------------------------------- #
# sign_test
# --------------------------------------------------------------------------- #

class TestSignTest:
    def test_all_positive_direction_positive(self):
        # 5/5 positive, direction "positive": exact binomial P(X>=5 | n=5,p=.5) = 1/32.
        result = fss.sign_test([1.0, 2.0, 3.0, 0.5, 0.1], "positive")
        assert result == {"k": 5, "n": 5, "p": pytest.approx(1 / 32)}

    def test_all_negative_direction_negative(self):
        result = fss.sign_test([-1.0, -2.0, -3.0, -0.5, -0.1], "negative")
        assert result == {"k": 5, "n": 5, "p": pytest.approx(1 / 32)}

    def test_mixed_3v2_not_significant(self):
        # 3 positive, 2 negative, direction "positive": k=3, n=5,
        # P(X>=3 | n=5, p=.5) = (C(5,3)+C(5,4)+C(5,5)) / 32 = (10+5+1)/32 = 16/32 = 0.5
        result = fss.sign_test([3.0, 3.0, 3.0, -3.0, -3.0], "positive")
        assert result["k"] == 3
        assert result["n"] == 5
        assert result["p"] == pytest.approx(0.5)

    def test_zero_diffs_excluded_from_n(self):
        # one exact zero excluded (tie); 3 positive out of remaining 4.
        result = fss.sign_test([1.0, 1.0, 1.0, -1.0, 0.0], "positive")
        assert result["k"] == 3
        assert result["n"] == 4

    def test_empty_returns_nan(self):
        result = fss.sign_test([], "positive")
        assert result["n"] == 0
        assert np.isnan(result["p"])


# --------------------------------------------------------------------------- #
# wilcoxon_test
# --------------------------------------------------------------------------- #

class TestWilcoxonTest:
    def test_matches_scipy_directly(self):
        from scipy import stats as scipy_stats

        diffs = [3.0, 3.0, 3.0, -3.0, -3.0]
        result = fss.wilcoxon_test(diffs, "positive")
        expected = scipy_stats.wilcoxon(diffs, alternative="greater")
        assert result["stat"] == pytest.approx(float(expected.statistic))
        assert result["p"] == pytest.approx(float(expected.pvalue))

    def test_direction_negative_uses_less(self):
        from scipy import stats as scipy_stats

        diffs = [-1.0, -2.0, -3.0, -0.5, -0.1]
        result = fss.wilcoxon_test(diffs, "negative")
        expected = scipy_stats.wilcoxon(diffs, alternative="less")
        assert result["p"] == pytest.approx(float(expected.pvalue))

    def test_all_zero_diffs_does_not_crash(self):
        result = fss.wilcoxon_test([0.0, 0.0, 0.0], "positive")
        assert np.isnan(result["p"])

    def test_empty_returns_nan(self):
        result = fss.wilcoxon_test([], "positive")
        assert np.isnan(result["p"])


# --------------------------------------------------------------------------- #
# holm_adjust -- known ordering, including a case that exercises the
# monotonic-enforcement clamp (a later sorted p*factor would otherwise DROP
# below the running max).
# --------------------------------------------------------------------------- #

class TestHolmAdjust:
    def test_simple_ascending_no_clamp_needed(self):
        # p = [0.001 (H1), 0.02 (H2), 0.04 (H3)], m=3, already sorted ascending.
        # H1: 0.001*3=0.003; H2: 0.02*2=0.04 (running_max=0.04);
        # H3: 0.04*1=0.04 (running_max stays 0.04).
        adjusted = fss.holm_adjust([0.001, 0.02, 0.04])
        assert adjusted == pytest.approx([0.003, 0.04, 0.04])

    def test_monotonic_enforcement_clamp(self):
        # p = [0.01 (H1), 0.03 (H2), 0.02 (H3)], m=3.
        # sorted ascending: H1(0.01,rank0,f3)->0.03; H3(0.02,rank1,f2)->0.04
        #   (running_max=0.04); H2(0.03,rank2,f1)->0.03, but must not go BELOW
        #   the running max -> clamped up to 0.04.
        # Expected, in original [H1, H2, H3] order: [0.03, 0.04, 0.04].
        adjusted = fss.holm_adjust([0.01, 0.03, 0.02])
        assert adjusted == pytest.approx([0.03, 0.04, 0.04])

    def test_result_is_monotonic_in_sorted_pvalue_order(self):
        pvals = [0.2, 0.001, 0.15]
        adjusted = fss.holm_adjust(pvals)
        order = np.argsort(pvals)
        sorted_adjusted = np.asarray(adjusted)[order]
        assert np.all(np.diff(sorted_adjusted) >= -1e-15)

    def test_capped_at_one(self):
        adjusted = fss.holm_adjust([0.9, 0.9, 0.9])
        assert all(v <= 1.0 for v in adjusted)

    def test_empty(self):
        assert fss.holm_adjust([]) == []


# --------------------------------------------------------------------------- #
# effect_floor -- known successive-diff arithmetic
# --------------------------------------------------------------------------- #

def _floor_fixture() -> pd.DataFrame:
    # Two seeds, prior arm, eps 0, severity 0.4: book_profit rises by a
    # constant step per generation, but the STEP differs by seed so the
    # pooled median is easy to hand-verify.
    rows = []
    for seed, step in ((1, 2.0), (2, 6.0)):
        for gen in range(4):  # generations 0..3 -> 3 successive diffs per seed
            rows.append(
                {
                    "seed": seed, "selection_severity": 0.4, "exploration_rate": 0.0,
                    "arm": "prior", "generation": gen, "policy": "prior",
                    "funded_rate": 0.6, "funded_default_rate": 0.1,
                    "book_profit": step * gen, "explored_profit": 0.0,
                    "declined_ece": 0.05,
                }
            )
    return fss._prepare(pd.DataFrame(rows))


class TestEffectFloor:
    def test_median_of_pooled_abs_diffs(self):
        df = _floor_fixture()
        # pooled abs diffs: seed1 -> [2,2,2], seed2 -> [6,6,6]; pooled 6 values
        # sorted: [2,2,2,6,6,6] -> median of 6 values = mean(2,6) = 4.0
        floor = fss.effect_floor(df, severity=0.4)
        assert floor == pytest.approx(4.0)

    def test_nan_when_no_matching_rows(self):
        df = _floor_fixture()
        floor = fss.effect_floor(df, severity=0.7)  # no such severity present
        assert np.isnan(floor)


# --------------------------------------------------------------------------- #
# h4_identity_check -- a consistent fixture (passes) and a broken one (fails)
# --------------------------------------------------------------------------- #

def _h4_fixture(broken: bool = False) -> pd.DataFrame:
    rows = []
    for seed in (1, 2):
        for gen in range(3):
            book_lo = 10.0 * gen + seed  # frozen, eps=0
            explored_hi = 1.5 if gen >= 1 else 0.0  # explored slice only from gen>=1
            book_hi = book_lo + explored_hi  # identity: hi - lo == explored_hi - 0
            if broken and seed == 2 and gen == 2:
                book_hi += 0.5  # inject a violation for one (seed, generation)
            rows.append(
                {
                    "seed": seed, "selection_severity": 0.4, "exploration_rate": 0.0,
                    "arm": "frozen", "generation": gen, "policy": "model",
                    "funded_rate": 0.6, "funded_default_rate": 0.1,
                    "book_profit": book_lo, "explored_profit": 0.0,
                    "declined_ece": 0.05,
                }
            )
            rows.append(
                {
                    "seed": seed, "selection_severity": 0.4, "exploration_rate": 0.05,
                    "arm": "frozen", "generation": gen, "policy": "model",
                    "funded_rate": 0.6, "funded_default_rate": 0.1,
                    "book_profit": book_hi, "explored_profit": explored_hi,
                    "declined_ece": 0.05,
                }
            )
    return fss._prepare(pd.DataFrame(rows))


class TestH4IdentityCheck:
    def test_consistent_fixture_passes(self):
        df = _h4_fixture(broken=False)
        result = fss.h4_identity_check(df, severity=0.4)
        assert result["passed"] is True
        assert result["n_checked"] == 6  # 2 seeds x 3 generations
        assert result["max_abs_error"] == pytest.approx(0.0, abs=1e-12)

    def test_broken_fixture_fails_with_known_error(self):
        df = _h4_fixture(broken=True)
        result = fss.h4_identity_check(df, severity=0.4)
        assert result["passed"] is False
        assert result["max_abs_error"] == pytest.approx(0.5)

    def test_no_matching_rows_fails_closed(self):
        df = _h4_fixture(broken=False)
        result = fss.h4_identity_check(df, severity=9.9)
        assert result["passed"] is False
        assert result["n_checked"] == 0


# --------------------------------------------------------------------------- #
# per_seed_paired_diffs
# --------------------------------------------------------------------------- #

class TestPerSeedPairedDiffs:
    def test_matches_hand_computation(self):
        rows = []
        for seed in (1, 2):
            for gen in range(3):
                rows.append(
                    {"seed": seed, "selection_severity": 0.4, "exploration_rate": 0.0,
                     "arm": "treatment", "generation": gen, "policy": "model",
                     "funded_rate": 0.6, "funded_default_rate": 0.1,
                     "book_profit": 10.0 * gen + seed, "explored_profit": 0.0,
                     "declined_ece": 0.05}
                )
                rows.append(
                    {"seed": seed, "selection_severity": 0.4, "exploration_rate": 0.0,
                     "arm": "frozen", "generation": gen, "policy": "model",
                     "funded_rate": 0.6, "funded_default_rate": 0.1,
                     "book_profit": 10.0 * gen + seed + 5.0, "explored_profit": 0.0,
                     "declined_ece": 0.05}
                )
        df = fss._prepare(pd.DataFrame(rows))
        diffs = fss.per_seed_paired_diffs(
            df, "treatment", 0.0, "frozen", 0.0, 0.4, "book_profit",
            generations=(1, 2),
        )
        # treatment - frozen = -5 at every generation for every seed.
        assert diffs == {1: pytest.approx(-5.0), 2: pytest.approx(-5.0)}


# --------------------------------------------------------------------------- #
# t_ece_distribution / summarize_t_ece
# --------------------------------------------------------------------------- #

class TestTEceDistribution:
    def test_first_alarm_generation_and_never(self):
        rows = []
        # seed 1: alarms at generation 2 (0.05 -> 0.15).
        for gen, ece in ((1, 0.05), (2, 0.15), (3, 0.20)):
            rows.append(
                {"seed": 1, "selection_severity": 0.4, "exploration_rate": 0.0,
                 "arm": "treatment", "generation": gen, "policy": "model",
                 "funded_rate": 0.6, "funded_default_rate": 0.1,
                 "book_profit": 1.0, "explored_profit": 0.0, "declined_ece": ece}
            )
        # seed 2: never alarms.
        for gen, ece in ((1, 0.02), (2, 0.03)):
            rows.append(
                {"seed": 2, "selection_severity": 0.4, "exploration_rate": 0.0,
                 "arm": "treatment", "generation": gen, "policy": "model",
                 "funded_rate": 0.6, "funded_default_rate": 0.1,
                 "book_profit": 1.0, "explored_profit": 0.0, "declined_ece": ece}
            )
        df = fss._prepare(pd.DataFrame(rows))
        t_ece = fss.t_ece_distribution(df, target=0.10)
        assert t_ece[(1, 0.4, 0.0)] == 2
        assert t_ece[(2, 0.4, 0.0)] is None

        summary = fss.summarize_t_ece(t_ece)
        cell = summary[(0.4, 0.0)]
        assert cell["n_runs"] == 2
        assert cell["counts"] == {"2": 1, "never": 1}
        assert cell["n_immediate_gen1"] == 0


# --------------------------------------------------------------------------- #
# End-to-end: build_stats_rows on a full hand-built fixture -- known signs,
# known Holm ordering (via the confirmatory family), known floor, H4 pass.
# --------------------------------------------------------------------------- #

def _full_fixture() -> pd.DataFrame:
    """8 seeds x severity 0.4 x arms {treatment, frozen, prior} x eps {0, 0.05},
    12 generations (0..11), constructed so every stat is hand-verifiable:

    - treatment_eps0(seed, gen) = 2*gen + seed
    - frozen_eps0   = treatment_eps0 + 5        -> H1 = treatment-frozen = -5 (8/8 negative)
    - prior_eps0    = frozen_eps0 + 5           -> H2 = frozen-prior     = -5 (8/8 negative)
      (n=8 so the exact sign-test p-value, 1/256, still clears a x3 Holm
      correction -- n=5's floor of 1/32 cannot, by construction of the exact
      binomial, regardless of effect size, which is the point: this fixture
      is sized to be able to demonstrate BOTH a confirmed and a not-confirmed
      hypothesis.)
    - treatment_eps.05 = treatment_eps0 + delta(seed), delta = +3 for seeds
      1-5 and -3 for seeds 6-8 -> H3 sign 5/8 positive (NOT significant)
    - explored_profit(treatment, eps.05, gen>=1) = 1.0, else 0.0
      -> H3a = (treatment_eps0+delta-explored) - (treatment_eps0-0)
             = delta - explored, so +2 for seeds 1-5 (gen>=1), -4 for seeds 6-8.
    - frozen_eps.05 = frozen_eps0 + explored_profit(frozen, eps.05, gen)
      with explored_profit(frozen, eps.05, gen>=1)=2.0 else 0.0 -> H4 exact.
    - prior arm eps0 successive-generation book_profit step is 2.0 for every
      seed and generation -> effect floor = 2.0 exactly.
    """
    rows = []
    seeds = (1, 2, 3, 4, 5, 6, 7, 8)
    for seed in seeds:
        delta = 3.0 if seed <= 5 else -3.0
        for gen in range(12):
            treatment_eps0 = 2.0 * gen + seed
            frozen_eps0 = treatment_eps0 + 5.0
            prior_eps0 = frozen_eps0 + 5.0
            explored_treat_hi = 1.0 if gen >= 1 else 0.0
            explored_frozen_hi = 2.0 if gen >= 1 else 0.0
            treatment_eps_hi = treatment_eps0 + delta

            common = {
                "seed": seed, "selection_severity": 0.4, "generation": gen,
                "policy": "prior" if gen == 0 else "model",
                "funded_rate": 0.6, "funded_default_rate": 0.1,
                "declined_ece": 0.03 if gen < 3 else 0.20,
            }
            rows.append({**common, "arm": "treatment", "exploration_rate": 0.0,
                         "book_profit": treatment_eps0, "explored_profit": 0.0})
            rows.append({**common, "arm": "treatment", "exploration_rate": 0.05,
                         "book_profit": treatment_eps_hi, "explored_profit": explored_treat_hi})
            rows.append({**common, "arm": "frozen", "exploration_rate": 0.0,
                         "book_profit": frozen_eps0, "explored_profit": 0.0})
            rows.append({**common, "arm": "frozen", "exploration_rate": 0.05,
                         "book_profit": frozen_eps0 + explored_frozen_hi,
                         "explored_profit": explored_frozen_hi})
            rows.append({**common, "arm": "prior", "exploration_rate": 0.0,
                         "book_profit": prior_eps0, "explored_profit": 0.0})
    return fss._prepare(pd.DataFrame(rows))


class TestBuildStatsRowsEndToEnd:
    def test_h1_h2_confirmed_h3_not(self):
        df = _full_fixture()
        rows = fss.build_stats_rows(df)
        by_key = {(r["metric"], r["hypothesis"], r["severity"]): r for r in rows}

        h1 = by_key[("hypothesis", "H1", 0.4)]
        assert h1["median_per_seed_stat"] == pytest.approx(-5.0)
        assert h1["sign_k"] == 8 and h1["sign_n"] == 8
        assert h1["floor"] == pytest.approx(2.0)
        assert h1["clears_floor"] is True
        assert h1["sign_p_raw"] == pytest.approx(1 / 256)
        assert h1["sign_p_holm"] == pytest.approx(3 / 256)  # Holm x3, still < 0.05
        assert h1["confirmed"] is True

        h2 = by_key[("hypothesis", "H2", 0.4)]
        assert h2["median_per_seed_stat"] == pytest.approx(-5.0)
        assert h2["confirmed"] is True

        h3 = by_key[("hypothesis", "H3", 0.4)]
        assert h3["sign_k"] == 5 and h3["sign_n"] == 8
        assert h3["confirmed"] is False  # sign test p=0.363, nowhere near alpha

    def test_h3a_matches_hand_calc(self):
        df = _full_fixture()
        rows = fss.build_stats_rows(df)
        h3a = next(r for r in rows if r["hypothesis"] == "H3a" and r["severity"] == 0.4)
        # per-seed mean over gens 1..11 of policy_book_profit diff:
        # seeds 1-5: delta(3) - explored(1) = +2 constant; seeds 6-8: -3-1=-4.
        assert h3a["sign_k"] == 5 and h3a["sign_n"] == 8  # 5 positive (seeds 1-5)

    def test_h4_identity_passes_on_construction(self):
        df = _full_fixture()
        rows = fss.build_stats_rows(df)
        h4 = next(r for r in rows if r["metric"] == "h4_identity" and r["severity"] == 0.4)
        assert h4["identity_passed"] is True
        assert h4["identity_max_abs_error"] == pytest.approx(0.0, abs=1e-9)

    def test_t_ece_reported(self):
        df = _full_fixture()
        rows = fss.build_stats_rows(df)
        t_ece_rows = [r for r in rows if r["metric"] == "t_ece_distribution"]
        assert len(t_ece_rows) >= 1
        cell = next(r for r in t_ece_rows if r["exploration_rate"] == 0.0)
        counts = json.loads(cell["detail_json"])
        # declined_ece jumps to 0.20 (> TARGET 0.10) at generation 3 for every seed.
        assert counts.get("3") == 8

    def test_holm_correction_only_at_confirmatory_severity(self):
        df = _full_fixture()
        rows = fss.build_stats_rows(df)
        for r in rows:
            if r["metric"] == "hypothesis" and r["hypothesis"] in ("H1", "H2", "H3"):
                if r["severity"] == 0.4:
                    assert not np.isnan(r["sign_p_holm"])
                else:
                    assert r["confirmed"] is None

    def test_write_stats_csv_roundtrips(self, tmp_path):
        df = _full_fixture()
        rows = fss.build_stats_rows(df)
        out = tmp_path / "feedback_sweep_stats.csv"
        frame = fss.write_stats_csv(rows, out=out)
        assert out.exists()
        reloaded = pd.read_csv(out)
        assert list(reloaded.columns) == fss.STATS_FIELDS
        assert len(reloaded) == len(frame) == len(rows)

    def test_print_ascii_summary_is_ascii_and_does_not_crash(self, tmp_path, capsys):
        df = _full_fixture()
        rows = fss.build_stats_rows(df)
        fss.print_ascii_summary(rows, out=tmp_path / "x.csv")
        captured = capsys.readouterr().out
        captured.encode("ascii")  # raises UnicodeEncodeError if any non-ASCII slipped in


# --------------------------------------------------------------------------- #
# Pilot mode: load_pilot_shards + main(--pilot) exit codes
# --------------------------------------------------------------------------- #

class TestPilotMode:
    def test_load_pilot_shards_concatenates_arbitrary_filenames(self, tmp_path):
        df1 = pd.DataFrame([
            {"seed": 1000, "selection_severity": 0.4, "exploration_rate": 0.0,
             "arm": "frozen", "generation": 0, "policy": "prior",
             "funded_rate": 0.6, "funded_default_rate": 0.1,
             "book_profit": 1.0, "explored_profit": 0.0, "declined_ece": 0.05},
        ])
        df2 = pd.DataFrame([
            {"seed": 1000, "selection_severity": 0.4, "exploration_rate": 0.05,
             "arm": "frozen", "generation": 0, "policy": "prior",
             "funded_rate": 0.6, "funded_default_rate": 0.1,
             "book_profit": 1.0, "explored_profit": 0.0, "declined_ece": 0.05},
        ])
        shard_dir = tmp_path / "parts"
        shard_dir.mkdir()
        df1.to_csv(shard_dir / "whatever_name_1.csv", index=False)
        df2.to_csv(shard_dir / "totally_different_2.csv", index=False)
        combined = fss.load_pilot_shards(shard_dir)
        assert len(combined) == 2

    def test_load_pilot_shards_raises_when_empty(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            fss.load_pilot_shards(tmp_path / "does_not_exist")

    def _write_pilot_shard(self, shard_dir: Path, broken: bool = False) -> None:
        shard_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for gen in range(3):
            book_lo = 10.0 * gen
            explored_hi = 1.5 if gen >= 1 else 0.0
            book_hi = book_lo + explored_hi + (0.5 if (broken and gen == 2) else 0.0)
            rows.append({"seed": 1000, "selection_severity": 0.4, "exploration_rate": 0.0,
                         "arm": "frozen", "generation": gen, "policy": "model",
                         "funded_rate": 0.6, "funded_default_rate": 0.1,
                         "book_profit": book_lo, "explored_profit": 0.0,
                         "declined_ece": 0.05})
            rows.append({"seed": 1000, "selection_severity": 0.4, "exploration_rate": 0.05,
                         "arm": "frozen", "generation": gen, "policy": "model",
                         "funded_rate": 0.6, "funded_default_rate": 0.1,
                         "book_profit": book_hi, "explored_profit": explored_hi,
                         "declined_ece": 0.05})
        pd.DataFrame(rows).to_csv(shard_dir / "pilot_shard.csv", index=False)

    def test_main_pilot_passes(self, tmp_path, monkeypatch, capsys):
        shard_dir = tmp_path / "parts"
        self._write_pilot_shard(shard_dir, broken=False)
        monkeypatch.setattr(fss, "SHARD_DIR", shard_dir)
        rc = fss.main(["--pilot"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PASS" in out
        out.encode("ascii")

    def test_main_pilot_fails_on_broken_identity(self, tmp_path, monkeypatch, capsys):
        shard_dir = tmp_path / "parts"
        self._write_pilot_shard(shard_dir, broken=True)
        monkeypatch.setattr(fss, "SHARD_DIR", shard_dir)
        rc = fss.main(["--pilot"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL" in out
        out.encode("ascii")


# --------------------------------------------------------------------------- #
# Full-mode CLI: missing input file fails loudly
# --------------------------------------------------------------------------- #

class TestFullModeMissingInput:
    def test_load_full_csv_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            fss.load_full_csv(tmp_path / "does_not_exist.csv")
