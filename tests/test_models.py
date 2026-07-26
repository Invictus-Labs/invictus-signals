"""Tests for invictus_signals.models."""
from __future__ import annotations

import pytest

from invictus_signals.models import (
    AlgoLine,
    Candle,
    ConvictionLevel,
    Direction,
    DNTResult,
    LineColor,
    LineType,
    PatternMatch,
    RegimeClass,
    RegimeClassification,
    RegimeId,
    TAState,
    ValidationStatus,
)


class TestCandle:
    def test_construction(self) -> None:
        c = Candle(timestamp=1000.0, open=100.0, high=105.0, low=98.0, close=103.0, volume=5000.0)
        assert c.timestamp == 1000.0
        assert c.open == 100.0
        assert c.high == 105.0
        assert c.low == 98.0
        assert c.close == 103.0
        assert c.volume == 5000.0

    def test_equality(self) -> None:
        c1 = Candle(0.0, 100.0, 105.0, 98.0, 103.0, 5000.0)
        c2 = Candle(0.0, 100.0, 105.0, 98.0, 103.0, 5000.0)
        assert c1 == c2

    def test_inequality(self) -> None:
        c1 = Candle(0.0, 100.0, 105.0, 98.0, 103.0, 5000.0)
        c2 = Candle(0.0, 100.0, 105.0, 98.0, 104.0, 5000.0)
        assert c1 != c2


class TestTAState:
    def test_required_fields(self) -> None:
        ta = TAState(
            ma_fast=502.0,
            ma_mid=498.0,
            ma_slow=490.0,
            ma_fast_slope=0.5,
            ma_mid_slope=0.3,
            bb_upper=510.0,
            bb_lower=490.0,
            bb_middle=500.0,
            bb_width=0.04,
            bb_upper_slope=0.4,
            volume_ma=1000.0,
            vwap=501.0,
        )
        assert ta.ma_fast == 502.0
        assert ta.ma_mid == 498.0
        assert ta.ma_slow == 490.0

    def test_extended_fields_default_to_neutral(self) -> None:
        ta = TAState(
            ma_fast=100.0, ma_mid=100.0, ma_slow=100.0,
            ma_fast_slope=0.0, ma_mid_slope=0.0,
            bb_upper=105.0, bb_lower=95.0, bb_middle=100.0,
            bb_width=0.1, bb_upper_slope=0.0,
            volume_ma=1000.0, vwap=100.0,
        )
        assert ta.rsi == 50.0
        assert ta.macd_histogram == 0.0
        assert ta.adx == 0.0
        assert ta.atr == 0.0
        assert ta.atr_pct == 0.0

    def test_bandwidth_percentile_fields_default_to_absent(self) -> None:
        # QA-swarm finding (2026-07-26): compute_ta_state's own tests always
        # pass these 3 fields explicitly, so they never exercise the
        # dataclass-level DEFAULT — a regression that flips
        # intraday_bb_width_pct's default from None to 0.0 (turning "not
        # computed" into "0th percentile / maximally compressed", the
        # strongest signal this field can emit) would pass the entire suite
        # undetected. Uses `is None`, never a falsy/truthiness check, so a
        # 0.0 default fails loudly rather than silently comparing equal.
        ta = TAState(
            ma_fast=100.0, ma_mid=100.0, ma_slow=100.0,
            ma_fast_slope=0.0, ma_mid_slope=0.0,
            bb_upper=105.0, bb_lower=95.0, bb_middle=100.0,
            bb_width=0.1, bb_upper_slope=0.0,
            volume_ma=1000.0, vwap=100.0,
        )
        assert ta.bb_width_pct is None
        assert ta.intraday_bb_width_pct is None
        assert ta.intraday_bb_width == 0.0

    def test_extended_fields_custom(self) -> None:
        ta = TAState(
            ma_fast=100.0, ma_mid=100.0, ma_slow=100.0,
            ma_fast_slope=0.0, ma_mid_slope=0.0,
            bb_upper=105.0, bb_lower=95.0, bb_middle=100.0,
            bb_width=0.1, bb_upper_slope=0.0,
            volume_ma=1000.0, vwap=100.0,
            rsi=65.0, macd_histogram=1.5, adx=25.0, atr=2.0, atr_pct=0.02,
        )
        assert ta.rsi == 65.0
        assert ta.macd_histogram == 1.5
        assert ta.adx == 25.0


class TestRegimeEnums:
    def test_regime_class_values(self) -> None:
        assert RegimeClass.BULLISH.value == "bullish"
        assert RegimeClass.BEARISH.value == "bearish"
        assert RegimeClass.CHOPPY.value == "choppy"
        assert RegimeClass.TRANSITION.value == "transition"

    def test_all_33_regime_ids_present(self) -> None:
        ids = {r.value for r in RegimeId}
        # Bullish: 8
        for prefix in ["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8"]:
            assert any(prefix in v for v in ids), f"Missing {prefix}"
        # Bearish: 8
        for prefix in ["br1", "br2", "br3", "br4", "br5", "br6", "br7", "br8"]:
            assert any(prefix in v for v in ids), f"Missing {prefix}"
        # Choppy: 8
        for prefix in ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]:
            assert any(prefix in v for v in ids), f"Missing {prefix}"
        # Transition: 9
        for prefix in ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9"]:
            assert any(prefix in v for v in ids), f"Missing {prefix}"

    def test_total_regime_count(self) -> None:
        assert len(RegimeId) == 33

    def test_direction_values(self) -> None:
        assert Direction.LONG.value == "long"
        assert Direction.SHORT.value == "short"


class TestLineModels:
    def test_line_color_count(self) -> None:
        assert len(LineColor) == 7

    def test_line_color_values(self) -> None:
        colors = {c.value for c in LineColor}
        for color in ("magenta", "orange", "green", "teal", "yellow", "pink", "blue"):
            assert color in colors

    def test_line_type_values(self) -> None:
        types = {t.value for t in LineType}
        assert "horizontal" in types
        assert "ascending_support" in types
        assert "descending_resistance" in types

    def test_algo_line_construction(self) -> None:
        line = AlgoLine(
            color=LineColor.ORANGE,
            line_type=LineType.ASCENDING_SUPPORT,
            touch_points=[(0.0, 100.0), (10.0, 101.0)],
            slope=0.1,
            current_level=102.0,
            session_frequency=0.80,
        )
        assert line.color == LineColor.ORANGE
        assert len(line.touch_points) == 2


class TestDNTResult:
    def test_construction(self) -> None:
        result = DNTResult(
            filter_id="dnt_01_no_structure",
            name="No Clear Algorithmic Structure",
            triggered=True,
            reason="Only 1 line with 2+ touches",
            frequency_pct=67.2,
        )
        assert result.triggered is True
        assert result.frequency_pct == 67.2


class TestConvictionAndValidation:
    def test_conviction_levels(self) -> None:
        assert ConvictionLevel.HIGH.value == "high"
        assert ConvictionLevel.MODERATE.value == "moderate"
        assert ConvictionLevel.LOW.value == "low"

    def test_validation_status_values(self) -> None:
        statuses = {s.value for s in ValidationStatus}
        assert "validated" in statuses
        assert "unvalidated" in statuses

    def test_pattern_match_construction(self) -> None:
        pm = PatternMatch(
            pattern_id="test_pattern",
            name="Test Pattern",
            direction=Direction.LONG,
            trigger_price=100.0,
            stop_price=98.0,
            target_prices=[105.0, 110.0],
            invalidation="Close below 97.0",
            confidence=0.8,
            lines_involved=[LineColor.ORANGE],
            frequency_pct=15.0,
            video_refs=["abc123"],
            validation_status=ValidationStatus.UNVALIDATED,
        )
        assert pm.pattern_id == "test_pattern"
        assert pm.direction == Direction.LONG


class TestRegimeClassification:
    def test_construction(self) -> None:
        rc = RegimeClassification(
            regime_id=RegimeId.B1_TRENDING,
            regime_class=RegimeClass.BULLISH,
            bias=Direction.LONG,
            size_multiplier=1.0,
            conditions_met=["price > fast MA"],
            confidence=0.90,
        )
        assert rc.regime_id == RegimeId.B1_TRENDING
        assert rc.bias == Direction.LONG
        assert rc.size_multiplier == 1.0
