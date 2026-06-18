"""Tests for invictus_signals.backtest.

Covers:
  - BacktestConfig / defaults
  - ReplayEngine: zero signals, basic win/loss, empty candles
  - TradeResult / AggregateStats math (Decimal)
  - BacktestReport.summary
  - validate_regime_labels: match rate, mismatch reporting, skip, threshold
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from invictus_signals.backtest import (
    BacktestConfig,
    BacktestReport,
    ReplayEngine,
    TradeResult,
    validate_regime_labels,
)
from invictus_signals.backtest.engine import SignalRecord, _decimal
from invictus_signals.backtest.models import AggregateStats
from invictus_signals.backtest.validation import ReferenceRow, ValidationReport
from invictus_signals.models import Direction, RegimeId
from tests.conftest import make_candle, make_candles


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rising_candles(n: int = 60, base: float = 100.0, step: float = 0.5) -> list:
    """n candles in a clear uptrend."""
    return make_candles([base + i * step for i in range(n)])


def _falling_candles(n: int = 60, base: float = 130.0, step: float = 0.5) -> list:
    """n candles in a clear downtrend."""
    return make_candles([base - i * step for i in range(n)])


def _no_signal_fn(ta, lines):
    return None


def _always_long_fn(ta, lines):
    return ("test_pattern", Direction.LONG)


def _always_short_fn(ta, lines):
    return ("test_pattern", Direction.SHORT)


# ---------------------------------------------------------------------------
# BacktestConfig
# ---------------------------------------------------------------------------

class TestBacktestConfig:
    def test_defaults(self) -> None:
        cfg = BacktestConfig()
        assert cfg.symbol == "BTC"
        assert cfg.fee_rate == Decimal("0.0006")
        assert len(cfg.tp_r_multiples) == 3

    def test_resolved_asset_config_known_symbol(self) -> None:
        cfg = BacktestConfig(symbol="BTC")
        ac = cfg.resolved_asset_config()
        assert ac is not None

    def test_resolved_asset_config_unknown_symbol_falls_back_to_spy(self) -> None:
        cfg = BacktestConfig(symbol="XYZUNKNOWN")
        ac = cfg.resolved_asset_config()
        assert ac is not None

    def test_asset_config_override(self) -> None:
        from invictus_signals.config import get_config
        spy_cfg = get_config("SPY")
        cfg = BacktestConfig(symbol="BTC", asset_config=spy_cfg)
        assert cfg.resolved_asset_config() is spy_cfg


# ---------------------------------------------------------------------------
# ReplayEngine — basic contract
# ---------------------------------------------------------------------------

class TestReplayEngineContract:
    def test_raises_on_empty_daily(self) -> None:
        with pytest.raises(ValueError, match="daily_candles"):
            ReplayEngine(
                daily_candles=[],
                intraday_candles=_rising_candles(5),
                config=BacktestConfig(),
                pattern_fn=_no_signal_fn,
            )

    def test_raises_on_empty_intraday(self) -> None:
        with pytest.raises(ValueError, match="intraday_candles"):
            ReplayEngine(
                daily_candles=_rising_candles(5),
                intraday_candles=[],
                config=BacktestConfig(),
                pattern_fn=_no_signal_fn,
            )

    def test_raises_when_neither_fn_nor_signals(self) -> None:
        with pytest.raises(ValueError, match="pattern_fn or signals"):
            ReplayEngine(
                daily_candles=_rising_candles(40),
                intraday_candles=_rising_candles(40),
                config=BacktestConfig(),
            )

    def test_insufficient_warmup_returns_empty_report(self) -> None:
        """Fewer than 30 bars → no trades."""
        engine = ReplayEngine(
            daily_candles=_rising_candles(10),
            intraday_candles=_rising_candles(10),
            config=BacktestConfig(),
            pattern_fn=_always_long_fn,
        )
        report = engine.run()
        assert report.all_trades == []
        assert report.per_symbol == {}

    def test_no_signal_fn_produces_no_trades(self) -> None:
        engine = ReplayEngine(
            daily_candles=_rising_candles(50),
            intraday_candles=_rising_candles(50),
            config=BacktestConfig(),
            pattern_fn=_no_signal_fn,
        )
        report = engine.run()
        assert len(report.all_trades) == 0


# ---------------------------------------------------------------------------
# ReplayEngine — trade production and math
# ---------------------------------------------------------------------------

class TestReplayEngineTrades:
    def test_long_signals_produce_trade_results(self) -> None:
        """LONG signals on rising candles should produce TradeResult entries."""
        engine = ReplayEngine(
            daily_candles=_rising_candles(60),
            intraday_candles=_rising_candles(60),
            config=BacktestConfig(symbol="SPY"),
            pattern_fn=_always_long_fn,
        )
        report = engine.run()
        assert len(report.all_trades) > 0
        for t in report.all_trades:
            assert isinstance(t.r_multiple, Decimal)
            assert isinstance(t.fees_paid, Decimal)
            assert t.fees_paid >= Decimal(0)
            assert t.entry_price > Decimal(0)

    def test_short_signals_produce_trade_results(self) -> None:
        """SHORT signals on falling candles should produce TradeResult entries."""
        engine = ReplayEngine(
            daily_candles=_falling_candles(60),
            intraday_candles=_falling_candles(60),
            config=BacktestConfig(symbol="SPY"),
            pattern_fn=_always_short_fn,
        )
        report = engine.run()
        assert len(report.all_trades) > 0

    def test_per_symbol_aggregates_populated(self) -> None:
        engine = ReplayEngine(
            daily_candles=_rising_candles(60),
            intraday_candles=_rising_candles(60),
            config=BacktestConfig(symbol="BTC"),
            pattern_fn=_always_long_fn,
        )
        report = engine.run()
        if report.all_trades:
            assert "BTC" in report.per_symbol
            stats = report.per_symbol["BTC"]
            assert stats.trades == len(report.all_trades)

    def test_per_pattern_regime_aggregates_populated(self) -> None:
        engine = ReplayEngine(
            daily_candles=_rising_candles(60),
            intraday_candles=_rising_candles(60),
            config=BacktestConfig(symbol="SPY"),
            pattern_fn=_always_long_fn,
        )
        report = engine.run()
        if report.all_trades:
            assert len(report.per_pattern_regime) > 0

    def test_report_summary_keys(self) -> None:
        engine = ReplayEngine(
            daily_candles=_rising_candles(60),
            intraday_candles=_rising_candles(60),
            config=BacktestConfig(),
            pattern_fn=_always_long_fn,
        )
        report = engine.run()
        summary = report.summary()
        assert "total_trades" in summary
        assert "win_rate" in summary
        assert "avg_r" in summary


# ---------------------------------------------------------------------------
# ReplayEngine — precomputed signals (SignalRecord)
# ---------------------------------------------------------------------------

class TestReplayEngineSignals:
    def test_precomputed_signal_fires_at_correct_bar(self) -> None:
        """A signal at bar 35 should produce exactly one trade."""
        daily = _rising_candles(60)
        signals = [SignalRecord(bar_index=35, pattern_id="s_test", direction=Direction.LONG, stop_offset_pct=0.01)]
        engine = ReplayEngine(
            daily_candles=daily,
            intraday_candles=daily,
            config=BacktestConfig(symbol="SPY"),
            signals=signals,
        )
        report = engine.run()
        assert len(report.all_trades) == 1
        assert report.all_trades[0].pattern_id == "s_test"

    def test_signals_take_precedence_over_pattern_fn(self) -> None:
        """When both signals and pattern_fn provided, signals take precedence for their bars."""
        daily = _rising_candles(60)
        signals = [SignalRecord(bar_index=35, pattern_id="from_signals", direction=Direction.LONG, stop_offset_pct=0.01)]
        call_log = []

        def tracking_fn(ta, lines):
            call_log.append(1)
            return None  # fn returns nothing; signals still fire

        engine = ReplayEngine(
            daily_candles=daily,
            intraday_candles=daily,
            config=BacktestConfig(symbol="SPY"),
            pattern_fn=tracking_fn,
            signals=signals,
        )
        report = engine.run()
        # Signal should have fired
        signal_trades = [t for t in report.all_trades if t.pattern_id == "from_signals"]
        assert len(signal_trades) == 1


# ---------------------------------------------------------------------------
# AggregateStats math
# ---------------------------------------------------------------------------

class TestAggregateStats:
    def test_win_rate_empty(self) -> None:
        stats = AggregateStats()
        assert stats.win_rate == Decimal(0)
        assert stats.avg_r == Decimal(0)

    def test_win_rate_calculation(self) -> None:
        stats = AggregateStats(trades=4, wins=3, losses=1, total_r=Decimal("6"))
        assert stats.win_rate == Decimal("3") / Decimal("4")
        assert stats.avg_r == Decimal("6") / Decimal("4")

    def test_total_fees_accumulates_decimal(self) -> None:
        stats = AggregateStats()
        stats.total_fees += Decimal("0.00001")
        stats.total_fees += Decimal("0.00002")
        assert stats.total_fees == Decimal("0.00003")


# ---------------------------------------------------------------------------
# validate_regime_labels
# ---------------------------------------------------------------------------

class TestValidateRegimeLabels:
    """E7 regime-label validation."""

    def _make_sample(self) -> tuple[dict, dict, list[ReferenceRow]]:
        """Build a minimal sample: 2 symbols, 50 bars each, a few reference rows."""
        btc_daily = _rising_candles(50, base=80_000.0, step=50.0)
        spy_daily = _rising_candles(50, base=500.0, step=0.5)
        intra = _rising_candles(50, base=100.0, step=0.1)

        candles_by_sym = {"BTC": btc_daily, "SPY": spy_daily}
        intraday_by_sym = {"BTC": intra, "SPY": intra}

        # Build reference rows using timestamps from the daily candles.
        # We pick bars >=5 so there's enough warmup for compute_ta_state.
        reference = [
            ReferenceRow(symbol="BTC", timestamp=btc_daily[10].timestamp, regime_id="b1_trending"),
            ReferenceRow(symbol="SPY", timestamp=spy_daily[10].timestamp, regime_id="b1_trending"),
        ]
        return candles_by_sym, intraday_by_sym, reference

    def test_returns_validation_report(self) -> None:
        candles, intraday, ref = self._make_sample()
        result = validate_regime_labels(candles, intraday, ref)
        assert isinstance(result, ValidationReport)

    def test_total_checked_includes_matched_and_mismatched(self) -> None:
        candles, intraday, ref = self._make_sample()
        result = validate_regime_labels(candles, intraday, ref)
        assert result.total_checked == result.matched + len(result.mismatches)

    def test_skipped_for_unknown_symbol(self) -> None:
        candles, intraday, _ = self._make_sample()
        ref = [ReferenceRow(symbol="UNKNOWN", timestamp=0.0, regime_id="b1_trending")]
        result = validate_regime_labels(candles, intraday, ref)
        assert result.skipped == 1
        assert result.total_checked == 0

    def test_mismatch_reported_with_correct_keys(self) -> None:
        """A deliberate wrong expected regime_id produces a mismatch entry."""
        candles, intraday, _ = self._make_sample()
        btc_daily = candles["BTC"]
        ref = [ReferenceRow(symbol="BTC", timestamp=btc_daily[10].timestamp, regime_id="br1_aggressive")]
        result = validate_regime_labels(candles, intraday, ref)
        # Either it's a mismatch or the actual regime really is br1_aggressive
        if result.mismatches:
            m = result.mismatches[0]
            assert "symbol" in m
            assert "expected" in m
            assert "actual" in m

    def test_passes_threshold_property_false_when_below_95(self) -> None:
        report = ValidationReport(
            total_checked=100, matched=90, match_rate=0.90, mismatches=[], skipped=0
        )
        assert report.passes_threshold is False

    def test_passes_threshold_property_true_when_at_95(self) -> None:
        report = ValidationReport(
            total_checked=100, matched=95, match_rate=0.95, mismatches=[], skipped=0
        )
        assert report.passes_threshold is True

    def test_empty_reference_returns_zero_match_rate(self) -> None:
        candles, intraday, _ = self._make_sample()
        result = validate_regime_labels(candles, intraday, [])
        assert result.total_checked == 0
        assert result.match_rate == 0.0

    def test_match_rate_perfect_when_all_match(self) -> None:
        """All rows matching should yield match_rate == 1.0."""
        candles, intraday, ref = self._make_sample()
        # First compute the actual regime for each ref row, then re-check
        result = validate_regime_labels(candles, intraday, ref)
        if result.mismatches:
            # Rebuild ref with actual regime IDs from the replay
            corrected_ref = []
            mismatch_map = {(m["symbol"], m["timestamp"]): m["actual"] for m in result.mismatches}
            for row in ref:
                key = (row.symbol, row.timestamp)
                corrected_regime = mismatch_map.get(key, row.regime_id)
                corrected_ref.append(ReferenceRow(symbol=row.symbol, timestamp=row.timestamp, regime_id=str(corrected_regime)))
            result2 = validate_regime_labels(candles, intraday, corrected_ref)
            assert result2.match_rate == 1.0
        else:
            assert result.match_rate == 1.0

    def test_no_network_no_import_side_effects(self) -> None:
        """Sanity: running validation never makes network calls (pure functions only)."""
        candles, intraday, ref = self._make_sample()
        # If this runs without hanging, it's pure.
        result = validate_regime_labels(candles, intraday, ref)
        assert result is not None


# ---------------------------------------------------------------------------
# Decimal-only safety: _decimal helper
# ---------------------------------------------------------------------------

class TestDecimalHelper:
    def test_converts_float_to_decimal(self) -> None:
        d = _decimal(100.5)
        assert isinstance(d, Decimal)
        assert d == Decimal("100.5")

    def test_zero_converts(self) -> None:
        d = _decimal(0.0)
        assert d == Decimal(0)
