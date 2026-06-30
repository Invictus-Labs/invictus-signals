"""Tests for invictus_signals.dnt_filters."""
from __future__ import annotations

import pytest

from invictus_signals.config import get_config
from invictus_signals.dnt_filters import (
    dnt_01_no_structure,
    dnt_02_choppy,
    dnt_03_no_breakout_confirmation,
    dnt_04_inside_wedge,
    dnt_05_trapped_between_mas,
    dnt_06_no_short_uptrend,
    dnt_07_chasing_missed_entry,
    dnt_08_overtrading,
    dnt_09_buying_downtrend,
    dnt_10_news_no_structure,
    dnt_11_emotional_trading,
    dnt_12_low_volume,
    dnt_13_consecutive_losses,
    dnt_16_extended_at_bb,
    dnt_17_risk_undefined,
    run_universal_dnt_filters,
)
from invictus_signals.models import (
    AlgoLine,
    Candle,
    Direction,
    LineColor,
    LineType,
    RegimeClass,
    TAState,
)
from tests.conftest import make_candle, make_candles


def make_ta(
    ma_fast: float = 100.0,
    ma_mid: float = 100.0,
    ma_fast_slope: float = 0.0,
    bb_upper: float = 105.0,
    bb_lower: float = 95.0,
    bb_middle: float = 100.0,
    intraday_ma_fast: float = 0.0,
    intraday_close_slope: float = 0.0,
    intraday_adx: float = 0.0,
    intraday_ma_mid: float = 0.0,
    intraday_bb_upper: float = 0.0,
    intraday_bb_lower: float = 0.0,
) -> TAState:
    return TAState(
        ma_fast=ma_fast, ma_mid=ma_mid, ma_slow=90.0,
        ma_fast_slope=ma_fast_slope, ma_mid_slope=0.0,
        bb_upper=bb_upper, bb_lower=bb_lower, bb_middle=bb_middle,
        bb_width=0.1, bb_upper_slope=0.0, volume_ma=1000.0, vwap=100.0,
        intraday_ma_fast=intraday_ma_fast,
        intraday_close_slope=intraday_close_slope,
        intraday_adx=intraday_adx,
        intraday_ma_mid=intraday_ma_mid,
        intraday_bb_upper=intraday_bb_upper,
        intraday_bb_lower=intraday_bb_lower,
    )


def make_line(touches: int = 2) -> AlgoLine:
    return AlgoLine(
        color=LineColor.ORANGE,
        line_type=LineType.HORIZONTAL,
        touch_points=[(float(i), 100.0) for i in range(touches)],
        slope=0.0,
        current_level=100.0,
        session_frequency=0.80,
    )


class TestDNT01:
    def test_triggers_when_no_qualified_lines(self) -> None:
        result = dnt_01_no_structure([])
        assert result.triggered is True
        assert result.filter_id == "dnt_01_no_structure"

    def test_triggers_with_only_one_qualified(self) -> None:
        result = dnt_01_no_structure([make_line(2)])
        assert result.triggered is True

    def test_not_triggered_with_two_qualified(self) -> None:
        result = dnt_01_no_structure([make_line(2), make_line(3)])
        assert result.triggered is False

    def test_ignores_lines_with_insufficient_touches(self) -> None:
        lines = [make_line(1), make_line(2), make_line(1)]
        result = dnt_01_no_structure(lines)
        assert result.triggered is True  # Only 1 qualified


class TestDNT02:
    def test_triggers_on_choppy_range(self) -> None:
        candles = make_candles([100.0] * 70)  # Zero range
        result = dnt_02_choppy(candles, choppy_range_threshold=1.0)
        assert result.triggered is True

    def test_not_triggered_on_trending(self) -> None:
        prices = [100.0 + i * 0.5 for i in range(70)]
        candles = make_candles(prices)
        result = dnt_02_choppy(candles, choppy_range_threshold=1.0)
        assert result.triggered is False

    def test_btc_threshold_is_larger(self) -> None:
        # Range of 100 points would not trigger for SPY (thresh=1.0) but might for BTC (thresh=500)
        prices = [80000.0 + i * 2 for i in range(70)]  # 138 pt range
        candles = make_candles(prices)
        spy_result = dnt_02_choppy(candles, choppy_range_threshold=1.0)
        btc_result = dnt_02_choppy(candles, choppy_range_threshold=500.0)
        assert spy_result.triggered is False
        assert btc_result.triggered is True  # 138 < 500


class TestDNT03:
    def test_triggers_when_no_consecutive_closes(self) -> None:
        candles = make_candles([99.0, 100.5, 99.5, 100.5, 99.5])
        result = dnt_03_no_breakout_confirmation(candles, 100.0, Direction.LONG)
        assert result.triggered is True

    def test_not_triggered_with_two_consecutive(self) -> None:
        candles = make_candles([99.0, 99.0, 100.5, 101.0, 101.5])
        result = dnt_03_no_breakout_confirmation(candles, 100.0, Direction.LONG)
        assert result.triggered is False

    def test_short_direction(self) -> None:
        candles = make_candles([101.0, 99.0, 98.5, 99.0, 101.0])
        result = dnt_03_no_breakout_confirmation(candles, 100.0, Direction.SHORT)
        assert result.triggered is False  # 2 consecutive closes below 100


class TestDNT04:
    def test_triggers_when_inside_wedge(self) -> None:
        candles = make_candles([102.0, 102.5, 103.0, 102.5, 102.0])
        result = dnt_04_inside_wedge(candles, wedge_upper=104.0, wedge_lower=101.0)
        assert result.triggered is True

    def test_not_triggered_when_closed_outside(self) -> None:
        candles = make_candles([102.0, 103.0, 105.0, 103.0, 102.0])  # One close above wedge
        result = dnt_04_inside_wedge(candles, wedge_upper=104.0, wedge_lower=101.0)
        assert result.triggered is False


class TestDNT05:
    def test_triggers_when_between_mas(self) -> None:
        ta = make_ta(ma_fast=99.0, ma_mid=101.0)
        result = dnt_05_trapped_between_mas(100.0, ta)
        assert result.triggered is True

    def test_not_triggered_above_both(self) -> None:
        ta = make_ta(ma_fast=99.0, ma_mid=98.0)
        result = dnt_05_trapped_between_mas(100.0, ta)
        assert result.triggered is False

    def test_not_triggered_below_both(self) -> None:
        ta = make_ta(ma_fast=102.0, ma_mid=103.0)
        result = dnt_05_trapped_between_mas(100.0, ta)
        assert result.triggered is False

    def test_intraday_band_overrides_daily(self) -> None:
        # Intraday band present -> the intraday MAs decide. Price 100 is between
        # the intraday band (99-101) even though daily MAs say otherwise.
        ta = make_ta(
            ma_fast=200.0, ma_mid=300.0,  # daily band far away (would not trigger)
            intraday_ma_fast=99.0, intraday_ma_mid=101.0,
        )
        result = dnt_05_trapped_between_mas(100.0, ta)
        assert result.triggered is True

    def test_daily_band_stale_does_not_trap_when_intraday_clear(self) -> None:
        # Regression for dnt_05/HYPE 2026-06-05 (223 consecutive fires): price
        # sits inside the STALE daily band (99-101) but has broken cleanly above
        # the intraday band (97-98). With the intraday lens it must NOT trigger.
        ta = make_ta(
            ma_fast=99.0, ma_mid=101.0,  # stale daily band would falsely trap 100
            intraday_ma_fast=97.0, intraday_ma_mid=98.0,
        )
        result = dnt_05_trapped_between_mas(100.0, ta)
        assert result.triggered is False

    def test_sentinel_falls_back_to_daily_band(self) -> None:
        # No intraday data (0.0 sentinel) -> original daily-MA behavior.
        ta = make_ta(ma_fast=99.0, ma_mid=101.0)  # intraday_* default 0.0
        result = dnt_05_trapped_between_mas(100.0, ta)
        assert result.triggered is True


class TestDNT06:
    def test_triggers_when_shorting_uptrend(self) -> None:
        ta = make_ta(ma_fast_slope=0.5)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT)
        assert result.triggered is True

    def test_not_triggered_for_long(self) -> None:
        ta = make_ta(ma_fast_slope=0.5)
        result = dnt_06_no_short_uptrend(ta, Direction.LONG)
        assert result.triggered is False

    def test_not_triggered_when_slope_negative(self) -> None:
        ta = make_ta(ma_fast_slope=-0.5)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT)
        assert result.triggered is False

    def test_triggers_when_shorting_bullish_regime_flat_slope(self) -> None:
        # The leak: regime is BULLISH (price/MA structure up) but the 5-bar
        # close slope is flat/negative on a pullback. Slope-only gate missed it;
        # regime-aware gate now blocks the short. (2026-06-13 HYPE b7 regression.)
        ta = make_ta(ma_fast_slope=-0.5)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.BULLISH)
        assert result.triggered is True
        assert "BULLISH" in result.reason

    def test_zero_slope_bullish_regime_triggers(self) -> None:
        ta = make_ta(ma_fast_slope=0.0)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.BULLISH)
        assert result.triggered is True

    def test_not_triggered_shorting_bearish_regime(self) -> None:
        # Legit downtrend short must still fire — regime not bullish, slope down.
        ta = make_ta(ma_fast_slope=-0.5)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.BEARISH)
        assert result.triggered is False

    def test_slope_up_triggers_regardless_of_regime(self) -> None:
        ta = make_ta(ma_fast_slope=0.5)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.BEARISH)
        assert result.triggered is True

    def test_backcompat_no_regime_arg_is_slope_only(self) -> None:
        # Omitting regime_class preserves the original slope-only behaviour.
        ta = make_ta(ma_fast_slope=-0.5)
        assert dnt_06_no_short_uptrend(ta, Direction.SHORT).triggered is False
        ta_up = make_ta(ma_fast_slope=0.5)
        assert dnt_06_no_short_uptrend(ta_up, Direction.SHORT).triggered is True

    def test_long_not_applicable_even_in_bullish(self) -> None:
        ta = make_ta(ma_fast_slope=0.5)
        result = dnt_06_no_short_uptrend(ta, Direction.LONG, RegimeClass.BULLISH)
        assert result.triggered is False

    def test_not_triggered_in_choppy_regime(self) -> None:
        # CHOPPY is not a confirmed uptrend — shorts allowed (enum-coverage guard:
        # the BULLISH equality check is the whole safety mechanism).
        ta = make_ta(ma_fast_slope=-0.1)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.CHOPPY)
        assert result.triggered is False

    def test_not_triggered_in_transition_regime(self) -> None:
        # TRANSITION (incl. bullish-leaning T3/T8) is NOT classed BULLISH, so a
        # flat-slope short still passes. Documents the current scope boundary.
        ta = make_ta(ma_fast_slope=-0.1)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.TRANSITION)
        assert result.triggered is False

    def test_zero_slope_bullish_takes_regime_branch(self) -> None:
        ta = make_ta(ma_fast_slope=0.0)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.BULLISH)
        assert result.triggered is True
        assert "BULLISH" in result.reason

    def test_slope_up_branch_precedence_over_regime(self) -> None:
        # Both truthy: slope branch wins, reason cites slope (not regime).
        ta = make_ta(ma_fast_slope=0.5)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.BULLISH)
        assert result.triggered is True
        assert "slope" in result.reason


class TestDNT07:
    def test_triggers_when_chasing(self) -> None:
        # Price moved 2% above trigger (threshold 0.1%)
        result = dnt_07_chasing_missed_entry(
            current_price=102.0,
            trigger_level=100.0,
            direction=Direction.LONG,
            chase_threshold_pct=0.001,
        )
        assert result.triggered is True

    def test_not_triggered_within_threshold(self) -> None:
        # Price moved 0.05% above trigger (threshold 0.1%)
        result = dnt_07_chasing_missed_entry(
            current_price=100.05,
            trigger_level=100.0,
            direction=Direction.LONG,
            chase_threshold_pct=0.001,
        )
        assert result.triggered is False

    def test_short_direction(self) -> None:
        # Short: price fell below trigger by 2% (chasing down)
        result = dnt_07_chasing_missed_entry(
            current_price=98.0,
            trigger_level=100.0,
            direction=Direction.SHORT,
            chase_threshold_pct=0.001,
        )
        assert result.triggered is True

    def test_btc_wider_threshold(self) -> None:
        # BTC chase_threshold_pct = 0.003 (0.3%) vs SPY 0.001 (0.1%)
        # Price moved 0.2% — SPY triggers, BTC does not
        result_spy = dnt_07_chasing_missed_entry(80_200.0, 80_000.0, Direction.LONG, 0.001)
        result_btc = dnt_07_chasing_missed_entry(80_200.0, 80_000.0, Direction.LONG, 0.003)
        assert result_spy.triggered is True
        assert result_btc.triggered is False


class TestDNT08:
    def test_triggers_at_max(self) -> None:
        result = dnt_08_overtrading(3, max_trades=3)
        assert result.triggered is True

    def test_not_triggered_below_max(self) -> None:
        result = dnt_08_overtrading(2, max_trades=3)
        assert result.triggered is False

    def test_zero_trades(self) -> None:
        result = dnt_08_overtrading(0, max_trades=3)
        assert result.triggered is False


class TestDNT09:
    def test_triggers_buying_downtrend(self) -> None:
        ta = make_ta(ma_mid=105.0, ma_fast_slope=-0.5)
        result = dnt_09_buying_downtrend(ta, current_price=100.0, intended_direction=Direction.LONG)
        assert result.triggered is True

    def test_not_triggered_for_short(self) -> None:
        ta = make_ta(ma_mid=105.0, ma_fast_slope=-0.5)
        result = dnt_09_buying_downtrend(ta, current_price=100.0, intended_direction=Direction.SHORT)
        assert result.triggered is False

    def test_not_triggered_in_uptrend(self) -> None:
        ta = make_ta(ma_mid=95.0, ma_fast_slope=0.5)
        result = dnt_09_buying_downtrend(ta, current_price=100.0, intended_direction=Direction.LONG)
        assert result.triggered is False

    def test_daily_knife_released_by_intraday_recovery(self) -> None:
        # Regression: 2026-06-06/07 — 530 consecutive LONG blocks on
        # BTC/ETH/SOL/BNB through an intraday V-recovery. Daily slope stays
        # negative ~5 days and price sits below the 26d SMA for weeks after a
        # multi-day dump; the release must come from intraday structure.
        # Values from the live BTC block at 2026-06-07 14:09 UTC.
        ta = make_ta(
            ma_mid=73294.87, ma_fast_slope=-787.52,
            intraday_ma_fast=61300.0, intraday_close_slope=180.0,
        )
        result = dnt_09_buying_downtrend(
            ta, current_price=61705.81, intended_direction=Direction.LONG
        )
        assert result.triggered is False
        assert "RELEASED" in result.reason

    def test_daily_knife_still_triggers_when_intraday_falling(self) -> None:
        # The actual knife: intraday also falling — no release.
        ta = make_ta(
            ma_mid=105.0, ma_fast_slope=-0.5,
            intraday_ma_fast=102.0, intraday_close_slope=-0.5,
        )
        result = dnt_09_buying_downtrend(ta, current_price=100.0, intended_direction=Direction.LONG)
        assert result.triggered is True
        assert "falling knife" in result.reason

    def test_no_release_when_price_above_intraday_ma_but_slope_flat(self) -> None:
        # Both legs of the release are required: slope must be strictly > 0.
        ta = make_ta(
            ma_mid=105.0, ma_fast_slope=-0.5,
            intraday_ma_fast=98.0, intraday_close_slope=0.0,
        )
        result = dnt_09_buying_downtrend(ta, current_price=100.0, intended_direction=Direction.LONG)
        assert result.triggered is True

    def test_no_release_when_slope_up_but_price_below_intraday_ma(self) -> None:
        ta = make_ta(
            ma_mid=105.0, ma_fast_slope=-0.5,
            intraday_ma_fast=102.0, intraday_close_slope=0.5,
        )
        result = dnt_09_buying_downtrend(ta, current_price=100.0, intended_direction=Direction.LONG)
        assert result.triggered is True

    def test_backward_compat_without_intraday_data(self) -> None:
        # TAState built without intraday fields (0.0 sentinel) keeps the
        # original daily-only behavior — the release never applies.
        ta = make_ta(ma_mid=105.0, ma_fast_slope=-0.5)
        result = dnt_09_buying_downtrend(ta, current_price=100.0, intended_direction=Direction.LONG)
        assert result.triggered is True


class TestDNT10:
    def test_triggers_event_no_structure(self) -> None:
        result = dnt_10_news_no_structure(has_pending_event=True, lines=[])
        assert result.triggered is True

    def test_not_triggered_event_with_structure(self) -> None:
        result = dnt_10_news_no_structure(has_pending_event=True, lines=[make_line(2)])
        assert result.triggered is False

    def test_not_triggered_no_event(self) -> None:
        result = dnt_10_news_no_structure(has_pending_event=False, lines=[])
        assert result.triggered is False


class TestDNT11:
    def test_triggers_without_pattern(self) -> None:
        result = dnt_11_emotional_trading(has_pattern_signal=False)
        assert result.triggered is True

    def test_not_triggered_with_pattern(self) -> None:
        result = dnt_11_emotional_trading(has_pattern_signal=True)
        assert result.triggered is False


class TestDNT12:
    def test_triggers_low_volume(self) -> None:
        result = dnt_12_low_volume(current_volume=400.0, volume_baseline=1000.0, threshold=0.5)
        assert result.triggered is True

    def test_not_triggered_normal_volume(self) -> None:
        result = dnt_12_low_volume(current_volume=600.0, volume_baseline=1000.0, threshold=0.5)
        assert result.triggered is False

    def test_not_triggered_no_baseline(self) -> None:
        result = dnt_12_low_volume(current_volume=100.0, volume_baseline=0.0)
        assert result.triggered is False


class TestDNT13:
    def test_triggers_at_max_losses(self) -> None:
        result = dnt_13_consecutive_losses(2, max_losses=2)
        assert result.triggered is True

    def test_not_triggered_below_max(self) -> None:
        result = dnt_13_consecutive_losses(1, max_losses=2)
        assert result.triggered is False


class TestDNT16:
    def test_long_triggers_at_bb_upper(self) -> None:
        ta = make_ta(bb_upper=105.0, bb_lower=95.0)
        result = dnt_16_extended_at_bb(105.0, ta, Direction.LONG)
        assert result.triggered is True

    def test_long_not_triggered_below_bb(self) -> None:
        ta = make_ta(bb_upper=105.0, bb_lower=95.0)
        result = dnt_16_extended_at_bb(103.0, ta, Direction.LONG)
        assert result.triggered is False

    def test_short_triggers_at_bb_lower(self) -> None:
        ta = make_ta(bb_upper=105.0, bb_lower=95.0)
        result = dnt_16_extended_at_bb(95.0, ta, Direction.SHORT)
        assert result.triggered is True

    def test_short_not_triggered_above_bb(self) -> None:
        ta = make_ta(bb_upper=105.0, bb_lower=95.0)
        result = dnt_16_extended_at_bb(98.0, ta, Direction.SHORT)
        assert result.triggered is False

    def test_intraday_bb_overrides_daily_long(self) -> None:
        # Intraday BB present -> price tested against the intraday upper band.
        # Price 102 is below the stale daily upper (110) but >= intraday upper
        # (101), so the long IS overextended on the entry timeframe.
        ta = make_ta(
            bb_upper=110.0, bb_lower=90.0,  # stale daily band would not trigger
            intraday_bb_upper=101.0, intraday_bb_lower=99.0,
        )
        result = dnt_16_extended_at_bb(102.0, ta, Direction.LONG)
        assert result.triggered is True

    def test_intraday_bb_overrides_daily_no_false_block(self) -> None:
        # Regression: price >= stale daily upper (105) but still inside the
        # intraday band (upper 108) -> not extended on the entry timeframe.
        ta = make_ta(
            bb_upper=105.0, bb_lower=95.0,  # stale daily band would falsely block
            intraday_bb_upper=108.0, intraday_bb_lower=102.0,
        )
        result = dnt_16_extended_at_bb(106.0, ta, Direction.LONG)
        assert result.triggered is False

    def test_sentinel_falls_back_to_daily_bb(self) -> None:
        # No intraday BB (0.0 sentinel) -> original daily-BB behavior.
        ta = make_ta(bb_upper=105.0, bb_lower=95.0)  # intraday_bb_* default 0.0
        result = dnt_16_extended_at_bb(105.0, ta, Direction.LONG)
        assert result.triggered is True


class TestDNT17:
    def test_triggers_poor_rr(self) -> None:
        result = dnt_17_risk_undefined(
            entry_price=100.0, stop_price=99.0, target_price=101.0, min_rr=3.0
        )
        assert result.triggered is True  # R:R = 1.0 < 3.0

    def test_not_triggered_good_rr(self) -> None:
        result = dnt_17_risk_undefined(
            entry_price=100.0, stop_price=99.0, target_price=104.0, min_rr=3.0
        )
        assert result.triggered is False  # R:R = 4.0 >= 3.0

    def test_triggers_when_stop_equals_entry(self) -> None:
        result = dnt_17_risk_undefined(
            entry_price=100.0, stop_price=100.0, target_price=105.0
        )
        assert result.triggered is True


class TestRunUniversalDNTFilters:
    def test_returns_list(
        self, spy_candles_bullish, two_good_lines, regime_bullish, spy_ta_bullish
    ) -> None:
        results = run_universal_dnt_filters(
            spy_candles_bullish,
            two_good_lines,
            regime_bullish,
            spy_ta_bullish,
            trade_count=0,
            config=get_config("SPY"),
        )
        assert isinstance(results, list)
        assert len(results) > 0

    def test_dnt_14_triggers_through_dispatcher_in_chop(
        self, spy_candles_bullish, two_good_lines, regime_bullish
    ) -> None:
        """A low-intraday-ADX TAState must make dnt_14 fire via the aggregator.

        Guards the wiring: dnt_14 is appended in run_universal_dnt_filters and
        keys off cfg.min_intraday_adx (35.0). 0 < 15 < 35 => triggered.
        """
        ta_choppy = make_ta(intraday_adx=15.0)
        results = run_universal_dnt_filters(
            spy_candles_bullish, two_good_lines, regime_bullish, ta_choppy,
            trade_count=0, config=get_config("SPY"),
        )
        dnt_14 = next(
            (r for r in results if r.filter_id == "dnt_14_weak_intraday_trend"), None
        )
        assert dnt_14 is not None, "dnt_14 must be present in the aggregator results"
        assert dnt_14.triggered is True

    def test_dnt_14_passes_through_dispatcher_in_trend(
        self, spy_candles_bullish, two_good_lines, regime_bullish
    ) -> None:
        """A strongly-trending 1H (high intraday ADX) must NOT trip dnt_14."""
        ta_trend = make_ta(intraday_adx=50.0)
        results = run_universal_dnt_filters(
            spy_candles_bullish, two_good_lines, regime_bullish, ta_trend,
            trade_count=0, config=get_config("SPY"),
        )
        dnt_14 = next(
            (r for r in results if r.filter_id == "dnt_14_weak_intraday_trend"), None
        )
        assert dnt_14 is not None
        assert dnt_14.triggered is False

    def test_all_results_are_dnt_result(
        self, spy_candles_bullish, two_good_lines, regime_bullish, spy_ta_bullish
    ) -> None:
        from invictus_signals.models import DNTResult
        results = run_universal_dnt_filters(
            spy_candles_bullish, two_good_lines, regime_bullish, spy_ta_bullish, 0
        )
        for r in results:
            assert isinstance(r, DNTResult)
            assert r.filter_id.startswith("dnt_")

    def test_optional_filters_included_with_context(
        self, spy_candles_bullish, two_good_lines, regime_bullish, spy_ta_bullish
    ) -> None:
        """Filters 03, 04, 07, 17 only run when context provided."""
        results = run_universal_dnt_filters(
            spy_candles_bullish, two_good_lines, regime_bullish, spy_ta_bullish, 0,
            trigger_level=500.0,
            wedge_upper=510.0,
            wedge_lower=490.0,
            entry_price=500.0,
            stop_price=498.0,
            target_price=512.0,
        )
        filter_ids = {r.filter_id for r in results}
        assert "dnt_03_no_breakout_confirmation" in filter_ids
        assert "dnt_04_inside_wedge" in filter_ids
        assert "dnt_07_chasing_missed_entry" in filter_ids
        assert "dnt_17_risk_undefined" in filter_ids

    def test_dnt_06_blocks_short_in_bullish_regime_via_dispatcher(
        self, spy_candles_bullish, two_good_lines, regime_bullish
    ) -> None:
        """Regression (2026-06-13 HYPE b7 leak): a SHORT in a BULLISH regime
        with a flat/negative slope is gated through the dispatcher, even though
        the slope-only check alone would have let it through."""
        ta = make_ta(ma_fast_slope=-0.5)
        results = run_universal_dnt_filters(
            spy_candles_bullish, two_good_lines, regime_bullish, ta, 0,
            intended_direction=Direction.SHORT,
        )
        dnt06 = next(
            r for r in results if r.filter_id == "dnt_06_no_short_uptrend"
        )
        assert dnt06.triggered is True

    def test_btc_config_uses_correct_thresholds(
        self, two_good_lines, regime_bullish
    ) -> None:
        """BTC config choppy threshold = 500.0. SPY threshold = 1.0.
        Verify config's choppy_range_threshold is respected.
        """
        ta = TAState(
            ma_fast=84000.0, ma_mid=82000.0, ma_slow=80000.0,
            ma_fast_slope=100.0, ma_mid_slope=50.0,
            bb_upper=90000.0, bb_lower=78000.0, bb_middle=84000.0,
            bb_width=0.14, bb_upper_slope=80.0, volume_ma=500.0, vwap=84000.0,
        )
        # Create candles with exact zero high-low range
        flat_candles = [
            Candle(timestamp=float(i), open=84000.0, high=84000.0, low=84000.0,
                   close=84000.0, volume=1000.0)
            for i in range(70)
        ]
        spy_results = run_universal_dnt_filters(
            flat_candles, two_good_lines, regime_bullish, ta, 0,
            config=get_config("SPY"),
        )
        btc_results = run_universal_dnt_filters(
            flat_candles, two_good_lines, regime_bullish, ta, 0,
            config=get_config("BTC"),
        )
        spy_dnt02 = next(r for r in spy_results if r.filter_id == "dnt_02_choppy")
        btc_dnt02 = next(r for r in btc_results if r.filter_id == "dnt_02_choppy")
        # Zero range: both trigger (0 < 1.0 for SPY, 0 < 500 for BTC)
        assert spy_dnt02.triggered is True
        assert btc_dnt02.triggered is True

    def test_default_price_from_last_candle(
        self, two_good_lines, regime_bullish, spy_ta_bullish
    ) -> None:
        candles = make_candles([500.0] * 10)
        results = run_universal_dnt_filters(
            candles, two_good_lines, regime_bullish, spy_ta_bullish, 0
        )
        assert len(results) > 0


# ---------------------------------------------------------------------------
# E4: TRANSITION-regime bias coupling tests
# ---------------------------------------------------------------------------

class TestDNT06BiasCoupling:
    """E4: dnt_06 extended with regime_bias for TRANSITION regimes."""

    def test_back_compat_no_bias_arg_no_change(self) -> None:
        """Omitting regime_bias keeps byte-identical behaviour to prior release."""
        ta = make_ta(ma_fast_slope=-0.5)
        # No bias arg — should NOT trigger (negative slope, no bullish regime)
        result = dnt_06_no_short_uptrend(ta, Direction.SHORT, RegimeClass.TRANSITION)
        assert result.triggered is False

    def test_transition_long_bias_blocks_short(self) -> None:
        """T3_BULL_REVERSAL / T8_POST_BOUNCE carry bias=LONG — shorts blocked."""
        ta = make_ta(ma_fast_slope=-0.1)
        result = dnt_06_no_short_uptrend(
            ta, Direction.SHORT, RegimeClass.TRANSITION, regime_bias=Direction.LONG
        )
        assert result.triggered is True
        assert "TRANSITION" in result.reason
        assert "LONG" in result.reason

    def test_transition_short_bias_does_not_block_short(self) -> None:
        """bias=SHORT in TRANSITION (T5/T6) — short is allowed by dnt_06."""
        ta = make_ta(ma_fast_slope=-0.1)
        result = dnt_06_no_short_uptrend(
            ta, Direction.SHORT, RegimeClass.TRANSITION, regime_bias=Direction.SHORT
        )
        assert result.triggered is False

    def test_long_direction_never_blocked_even_with_bias_long(self) -> None:
        """dnt_06 only applies to SHORT direction."""
        ta = make_ta(ma_fast_slope=-0.1)
        result = dnt_06_no_short_uptrend(
            ta, Direction.LONG, RegimeClass.TRANSITION, regime_bias=Direction.LONG
        )
        assert result.triggered is False

    def test_slope_up_takes_precedence_over_bias_branch(self) -> None:
        """When slope_up is True the slope branch fires first (precedence check)."""
        ta = make_ta(ma_fast_slope=0.5)
        result = dnt_06_no_short_uptrend(
            ta, Direction.SHORT, RegimeClass.TRANSITION, regime_bias=Direction.LONG
        )
        assert result.triggered is True
        # Slope branch fires — reason should cite slope, not TRANSITION
        assert "slope" in result.reason.lower()

    def test_none_bias_with_transition_does_not_block(self) -> None:
        """regime_bias=None (default) with TRANSITION class: no block."""
        ta = make_ta(ma_fast_slope=-0.5)
        result = dnt_06_no_short_uptrend(
            ta, Direction.SHORT, RegimeClass.TRANSITION, regime_bias=None
        )
        assert result.triggered is False


class TestDNT09BiasCoupling:
    """E4: dnt_09 extended with regime_bias for TRANSITION regimes."""

    def test_back_compat_no_bias_arg_no_change(self) -> None:
        """Omitting regime_bias keeps byte-identical behaviour to prior release."""
        ta = make_ta(ma_mid=95.0, ma_fast_slope=0.5)
        result = dnt_09_buying_downtrend(
            ta, current_price=100.0, intended_direction=Direction.LONG
        )
        assert result.triggered is False

    def test_transition_short_bias_blocks_long(self) -> None:
        """T5_BEAR_REVERSAL / T6_HL_BREACH carry bias=SHORT — longs blocked."""
        ta = make_ta(ma_mid=95.0, ma_fast_slope=0.5)
        result = dnt_09_buying_downtrend(
            ta,
            current_price=100.0,
            intended_direction=Direction.LONG,
            regime_class=RegimeClass.TRANSITION,
            regime_bias=Direction.SHORT,
        )
        assert result.triggered is True
        assert "TRANSITION" in result.reason
        assert "SHORT" in result.reason

    def test_transition_long_bias_does_not_block_long(self) -> None:
        """bias=LONG in TRANSITION (T3/T8) — long is allowed by dnt_09."""
        ta = make_ta(ma_mid=95.0, ma_fast_slope=0.5)
        result = dnt_09_buying_downtrend(
            ta,
            current_price=100.0,
            intended_direction=Direction.LONG,
            regime_class=RegimeClass.TRANSITION,
            regime_bias=Direction.LONG,
        )
        assert result.triggered is False

    def test_short_direction_never_blocked_by_bias(self) -> None:
        """dnt_09 only applies to LONG direction."""
        ta = make_ta(ma_mid=95.0, ma_fast_slope=0.5)
        result = dnt_09_buying_downtrend(
            ta,
            current_price=100.0,
            intended_direction=Direction.SHORT,
            regime_class=RegimeClass.TRANSITION,
            regime_bias=Direction.SHORT,
        )
        assert result.triggered is False

    def test_daily_knife_and_transition_short_bias_both_active(self) -> None:
        """When both daily_knife AND transition_short_bias are active."""
        ta = make_ta(ma_mid=105.0, ma_fast_slope=-0.5)
        result = dnt_09_buying_downtrend(
            ta,
            current_price=100.0,
            intended_direction=Direction.LONG,
            regime_class=RegimeClass.TRANSITION,
            regime_bias=Direction.SHORT,
        )
        assert result.triggered is True
        # Reason should mention both conditions
        assert "ALSO" in result.reason or "regime TRANSITION" in result.reason

    def test_none_bias_with_transition_does_not_block(self) -> None:
        """regime_bias=None (default) with TRANSITION class: no block from bias."""
        ta = make_ta(ma_mid=95.0, ma_fast_slope=0.5)
        result = dnt_09_buying_downtrend(
            ta,
            current_price=100.0,
            intended_direction=Direction.LONG,
            regime_class=RegimeClass.TRANSITION,
            regime_bias=None,
        )
        assert result.triggered is False


# ---------------------------------------------------------------------------
# P1 DISPATCHER regression: run_universal_dnt_filters must thread regime.bias
# (These tests call via the aggregator — the path the bot actually uses.)
# ---------------------------------------------------------------------------

class TestDispatcherBiasCoupling:
    """Regression: E4 bias coupling was dead in production because
    run_universal_dnt_filters was not forwarding regime.bias to dnt_06/09.
    These tests exercise the full aggregator path, NOT the filter directly."""

    def test_dnt06_transition_long_bias_triggers_via_dispatcher(
        self, spy_candles_bullish, two_good_lines
    ) -> None:
        """TRANSITION regime + bias=LONG + SHORT direction → dnt_06 must trigger
        through the dispatcher.  Fails if aggregator omits regime_bias=."""
        from invictus_signals.models import RegimeId, RegimeClassification
        ta = make_ta(ma_fast_slope=-0.1)
        regime = RegimeClassification(
            regime_id=RegimeId.T3_BULL_REVERSAL,
            regime_class=RegimeClass.TRANSITION,
            bias=Direction.LONG,
            size_multiplier=0.75,
            conditions_met=["golden cross forming"],
            confidence=0.70,
        )
        results = run_universal_dnt_filters(
            spy_candles_bullish,
            two_good_lines,
            regime,
            ta,
            trade_count=0,
            intended_direction=Direction.SHORT,
        )
        dnt06 = next(r for r in results if r.filter_id == "dnt_06_no_short_uptrend")
        assert dnt06.triggered is True, (
            "E4 P1: dnt_06 must block shorts in T3/T8 TRANSITION+LONG-bias "
            "via the aggregator — bias was not threaded"
        )

    def test_dnt09_transition_short_bias_triggers_via_dispatcher(
        self, spy_candles_bullish, two_good_lines
    ) -> None:
        """TRANSITION regime + bias=SHORT + LONG direction → dnt_09 must trigger
        through the dispatcher.  Fails if aggregator omits regime_class/bias."""
        from invictus_signals.models import RegimeId, RegimeClassification
        # Daily conditions: no knife (slope positive, price above mid) so the
        # only trigger here is the TRANSITION+SHORT bias path.
        ta = make_ta(ma_mid=95.0, ma_fast_slope=0.5)
        regime = RegimeClassification(
            regime_id=RegimeId.T6_HL_BREACH,
            regime_class=RegimeClass.TRANSITION,
            bias=Direction.SHORT,
            size_multiplier=0.5,
            conditions_met=["price < mid MA", "fast slope < 0"],
            confidence=0.60,
        )
        results = run_universal_dnt_filters(
            spy_candles_bullish,
            two_good_lines,
            regime,
            ta,
            trade_count=0,
            intended_direction=Direction.LONG,
        )
        dnt09 = next(r for r in results if r.filter_id == "dnt_09_buying_downtrend")
        assert dnt09.triggered is True, (
            "E4 P1: dnt_09 must block longs in T5/T6 TRANSITION+SHORT-bias "
            "via the aggregator — regime_class/bias were not threaded"
        )

    def test_dnt06_choppy_bias_none_does_not_block_short(
        self, spy_candles_bullish, two_good_lines, regime_choppy
    ) -> None:
        """CHOPPY regime has bias=None — dnt_06 must NOT trigger on flat slope."""
        ta = make_ta(ma_fast_slope=-0.1)
        results = run_universal_dnt_filters(
            spy_candles_bullish,
            two_good_lines,
            regime_choppy,
            ta,
            trade_count=0,
            intended_direction=Direction.SHORT,
        )
        dnt06 = next(r for r in results if r.filter_id == "dnt_06_no_short_uptrend")
        assert dnt06.triggered is False

    def test_dnt09_choppy_bias_none_does_not_block_long(
        self, spy_candles_bullish, two_good_lines, regime_choppy
    ) -> None:
        """CHOPPY regime has bias=None — dnt_09 must NOT trigger when no daily knife."""
        ta = make_ta(ma_mid=95.0, ma_fast_slope=0.5)
        results = run_universal_dnt_filters(
            spy_candles_bullish,
            two_good_lines,
            regime_choppy,
            ta,
            trade_count=0,
            intended_direction=Direction.LONG,
        )
        dnt09 = next(r for r in results if r.filter_id == "dnt_09_buying_downtrend")
        assert dnt09.triggered is False
