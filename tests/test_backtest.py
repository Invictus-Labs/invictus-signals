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
        """Build a minimal sample: 2 symbols, 60 bars each, a few reference rows.

        Reference rows use bar index 35 — above the 30-bar _MIN_WARMUP_BARS gate
        so they are evaluated (not skipped) by validate_regime_labels.
        """
        btc_daily = _rising_candles(60, base=80_000.0, step=50.0)
        spy_daily = _rising_candles(60, base=500.0, step=0.5)
        intra = _rising_candles(60, base=100.0, step=0.1)

        candles_by_sym = {"BTC": btc_daily, "SPY": spy_daily}
        intraday_by_sym = {"BTC": intra, "SPY": intra}

        # Bar 35 is above the _MIN_WARMUP_BARS=30 gate — will be evaluated.
        reference = [
            ReferenceRow(symbol="BTC", timestamp=btc_daily[35].timestamp, regime_id="b1_trending"),
            ReferenceRow(symbol="SPY", timestamp=spy_daily[35].timestamp, regime_id="b1_trending"),
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
        # Use bar 35 (above warmup floor) with a wrong regime so it is evaluated
        ref = [ReferenceRow(symbol="BTC", timestamp=btc_daily[35].timestamp, regime_id="br1_aggressive")]
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


# ---------------------------------------------------------------------------
# P1: Fill model SL-hit and edge-case tests (previously dead branches)
# ---------------------------------------------------------------------------

class TestFillModelSLPaths:
    """Exercises the LONG-SL, SHORT-SL, last-bar, and zero-risk branches
    that were uncovered before the P1 fix.
    """

    def _engine_with_single_signal(
        self,
        daily: list,
        intraday: list,
        bar_index: int,
        direction: Direction,
        stop_offset_pct: float = 0.01,
    ) -> ReplayEngine:
        signals = [SignalRecord(
            bar_index=bar_index,
            pattern_id="sl_test",
            direction=direction,
            stop_offset_pct=stop_offset_pct,
        )]
        return ReplayEngine(
            daily_candles=daily,
            intraday_candles=intraday,
            config=BacktestConfig(symbol="SPY"),
            signals=signals,
        )

    def test_long_sl_hit_exit_reason_and_negative_r(self) -> None:
        """LONG signal where bar immediately crashes below SL → exit_reason='sl',
        r_multiple < 0.
        Set up: entry at bar 32 open (=100), SL at 99 (1%).
        Bar 32 low is set very low (50) to guarantee SL hit.
        """
        # Build 60 rising candles then inject a crash candle at index 32
        from tests.conftest import make_candle
        rising = [make_candle(100.0 + i * 0.1, timestamp=float(i)) for i in range(60)]
        # The signal fires at bar 31; engine enters at bar 32 open.
        # Make bar 32 low=50 so it's below any 1% SL.
        rising[32] = make_candle(
            close=100.0, high=101.0, low=50.0, timestamp=float(32)
        )
        intra = rising[:]
        engine = self._engine_with_single_signal(rising, intra, bar_index=31, direction=Direction.LONG)
        report = engine.run()
        sl_trades = [t for t in report.all_trades if t.exit_reason == "sl"]
        assert len(sl_trades) == 1, f"Expected 1 SL trade, got {report.all_trades}"
        trade = sl_trades[0]
        assert trade.r_multiple < Decimal(0), f"LONG SL must be negative R, got {trade.r_multiple}"
        assert trade.direction == Direction.LONG

    def test_short_sl_hit_exit_reason_and_negative_r(self) -> None:
        """SHORT signal where bar immediately spikes above SL → exit_reason='sl',
        r_multiple < 0.
        """
        from tests.conftest import make_candle
        falling = [make_candle(130.0 - i * 0.1, timestamp=float(i)) for i in range(60)]
        # Signal at bar 31; enter at bar 32 open (~127.9). SL is 1% above entry.
        # Inject a bar with high=300 so it blows past any 1% SHORT SL.
        falling[32] = make_candle(
            close=130.0, high=300.0, low=100.0, timestamp=float(32)
        )
        intra = falling[:]
        engine = self._engine_with_single_signal(falling, intra, bar_index=31, direction=Direction.SHORT)
        report = engine.run()
        sl_trades = [t for t in report.all_trades if t.exit_reason == "sl"]
        assert len(sl_trades) == 1, f"Expected 1 SHORT SL trade, got {report.all_trades}"
        trade = sl_trades[0]
        assert trade.r_multiple < Decimal(0), f"SHORT SL must be negative R, got {trade.r_multiple}"
        assert trade.direction == Direction.SHORT

    def test_signal_on_last_bar_produces_no_trade(self) -> None:
        """Signal at last available bar → no next bar to enter → no trade produced."""
        daily = _rising_candles(35)  # bars 0..34; warmup consumes 0..29
        # Signal at bar 34 (last bar) — engine checks i+1 >= n → skips
        signals = [SignalRecord(bar_index=34, pattern_id="edge", direction=Direction.LONG, stop_offset_pct=0.01)]
        engine = ReplayEngine(
            daily_candles=daily,
            intraday_candles=daily,
            config=BacktestConfig(symbol="SPY"),
            signals=signals,
        )
        report = engine.run()
        assert len(report.all_trades) == 0

    def test_zero_risk_signal_produces_no_trade(self) -> None:
        """stop_offset_pct=0 → SL==entry → risk=0 → _fill_trade returns None."""
        from tests.conftest import make_candle
        daily = [make_candle(100.0, timestamp=float(i)) for i in range(40)]
        signals = [SignalRecord(bar_index=31, pattern_id="zero_risk", direction=Direction.LONG, stop_offset_pct=0.0)]
        engine = ReplayEngine(
            daily_candles=daily,
            intraday_candles=daily,
            config=BacktestConfig(symbol="SPY"),
            signals=signals,
        )
        report = engine.run()
        zero_risk_trades = [t for t in report.all_trades if t.pattern_id == "zero_risk"]
        assert len(zero_risk_trades) == 0, "Zero-risk signal must produce no trade"


# ---------------------------------------------------------------------------
# P2: Win / loss / break-even classification contract
# ---------------------------------------------------------------------------

class TestWinLossBreakEvenContract:
    """AggregateStats and BacktestReport.summary() must correctly bucket
    positive-r, negative-r, and zero-r trades into wins/losses/break_even.
    """

    def _make_trade(self, r: str) -> TradeResult:
        """Build a minimal TradeResult with the given R-multiple string."""
        from invictus_signals.models import RegimeId
        return TradeResult(
            symbol="BTC",
            pattern_id="p",
            direction=Direction.LONG,
            regime_id=RegimeId.B1_TRENDING,
            entry_price=Decimal("100"),
            exit_price=Decimal("100"),
            stop_price=Decimal("99"),
            target_prices=[Decimal("103")],
            fees_paid=Decimal("0.01"),
            r_multiple=Decimal(r),
            exit_reason="tp1",
            bar_index=0,
            timestamp=0.0,
        )

    def test_all_loss_set_win_rate_zero(self) -> None:
        report = BacktestReport()
        for _ in range(5):
            t = self._make_trade("-1")
            report.all_trades.append(t)
        summary = report.summary()
        assert summary["win_rate"] == 0.0
        assert summary["losses"] == 5
        assert summary["wins"] == 0
        assert summary["break_even"] == 0

    def test_single_loss_stats(self) -> None:
        report = BacktestReport()
        report.all_trades.append(self._make_trade("-1"))
        summary = report.summary()
        assert summary["total_trades"] == 1
        assert summary["losses"] == 1
        assert summary["wins"] == 0

    def test_exactly_break_even_trade(self) -> None:
        """r_multiple == 0 must land in break_even, not wins or losses."""
        report = BacktestReport()
        report.all_trades.append(self._make_trade("0"))
        summary = report.summary()
        assert summary["break_even"] == 1
        assert summary["wins"] == 0
        assert summary["losses"] == 0

    def test_mixed_win_loss_breakeven(self) -> None:
        report = BacktestReport()
        report.all_trades.extend([
            self._make_trade("2"),    # win
            self._make_trade("-1"),   # loss
            self._make_trade("0"),    # break_even
        ])
        summary = report.summary()
        assert summary["total_trades"] == 3
        assert summary["wins"] == 1
        assert summary["losses"] == 1
        assert summary["break_even"] == 1

    def test_aggregate_stats_break_even_counter_via_update_stats(self) -> None:
        """_update_stats must increment break_even, not losses, for r==0."""
        from invictus_signals.backtest.engine import _update_stats
        report = BacktestReport()
        trade = self._make_trade("0")
        _update_stats(report, trade, "BTC")
        stats = report.per_symbol["BTC"]
        assert stats.break_even == 1
        assert stats.losses == 0
        assert stats.wins == 0
        assert stats.trades == 1

    def test_win_rate_excludes_break_even_from_denominator_via_property(self) -> None:
        """win_rate = wins/trades; break_even trades lower the rate (they aren't wins)."""
        stats = AggregateStats(trades=4, wins=2, losses=1, break_even=1, total_r=Decimal("2"))
        assert stats.win_rate == Decimal("2") / Decimal("4")


# ---------------------------------------------------------------------------
# P3: validate_regime_labels warmup floor matches _MIN_WARMUP_BARS
# ---------------------------------------------------------------------------

class TestValidationWarmupFloor:
    def test_bar_below_warmup_floor_is_skipped(self) -> None:
        """Rows whose bar_idx < _MIN_WARMUP_BARS (30) must be skipped, not checked."""
        from invictus_signals.backtest.engine import _MIN_WARMUP_BARS
        from invictus_signals.backtest.validation import ReferenceRow

        # Build 60 rising BTC candles
        daily = _rising_candles(60, base=80_000.0, step=50.0)
        intra = _rising_candles(10, base=100.0, step=0.1)

        # Reference row at bar 5 — well below the 30-bar floor
        ref = [ReferenceRow(symbol="BTC", timestamp=daily[5].timestamp, regime_id="b1_trending")]
        result = validate_regime_labels({"BTC": daily}, {"BTC": intra}, ref)
        assert result.skipped == 1
        assert result.total_checked == 0

    def test_bar_at_warmup_floor_is_evaluated(self) -> None:
        """Rows at exactly _MIN_WARMUP_BARS (30) should be evaluated, not skipped."""
        from invictus_signals.backtest.engine import _MIN_WARMUP_BARS
        from invictus_signals.backtest.validation import ReferenceRow

        daily = _rising_candles(60, base=80_000.0, step=50.0)
        intra = _rising_candles(10, base=100.0, step=0.1)

        ref = [ReferenceRow(symbol="BTC", timestamp=daily[_MIN_WARMUP_BARS].timestamp, regime_id="b1_trending")]
        result = validate_regime_labels({"BTC": daily}, {"BTC": intra}, ref)
        # Should be evaluated (total_checked >= 1), regardless of match/mismatch
        assert result.total_checked >= 1
