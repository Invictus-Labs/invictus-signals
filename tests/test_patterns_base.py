"""Tests for invictus_signals.patterns.base PatternDetector ABC."""
from __future__ import annotations

import pytest

from invictus_signals.models import (
    AlgoLine,
    Candle,
    Direction,
    LineColor,
    LineType,
    PatternMatch,
    RegimeClass,
    RegimeClassification,
    RegimeId,
    TAState,
    ValidationStatus,
)
from invictus_signals.patterns.base import PatternDetector


class ConcretePattern(PatternDetector):
    """Minimal concrete implementation for testing the ABC."""

    @property
    def pattern_id(self) -> str:
        return "test_pattern"

    @property
    def name(self) -> str:
        return "Test Pattern"

    @property
    def direction(self) -> Direction:
        return Direction.LONG

    @property
    def min_candles(self) -> int:
        return 10

    @property
    def frequency_pct(self) -> float:
        return 5.0

    def detect(
        self,
        candles: list[Candle],
        lines: list[AlgoLine],
        regime: RegimeClassification,
        ta_state: TAState,
    ) -> PatternMatch | None:
        if len(candles) < self.min_candles:
            return None
        return PatternMatch(
            pattern_id=self.pattern_id,
            name=self.name,
            direction=self.direction,
            trigger_price=candles[-1].close,
            stop_price=candles[-1].close * 0.99,
            target_prices=[candles[-1].close * 1.03],
            invalidation="Close below stop",
            confidence=0.7,
            lines_involved=[],
            frequency_pct=self.frequency_pct,
            video_refs=[],
            validation_status=ValidationStatus.UNVALIDATED,
        )


def make_ta() -> TAState:
    return TAState(
        ma_fast=100.0, ma_mid=98.0, ma_slow=95.0,
        ma_fast_slope=0.5, ma_mid_slope=0.3,
        bb_upper=105.0, bb_lower=95.0, bb_middle=100.0,
        bb_width=0.1, bb_upper_slope=0.3, volume_ma=1000.0, vwap=100.0,
    )


def make_regime() -> RegimeClassification:
    return RegimeClassification(
        regime_id=RegimeId.B1_TRENDING,
        regime_class=RegimeClass.BULLISH,
        bias=Direction.LONG,
        size_multiplier=1.0,
        conditions_met=["price > fast MA"],
        confidence=0.9,
    )


class TestPatternDetectorABC:
    def test_cannot_instantiate_abc_directly(self) -> None:
        with pytest.raises(TypeError):
            PatternDetector()  # type: ignore[abstract]

    def test_concrete_implementation_works(self) -> None:
        p = ConcretePattern()
        assert p.pattern_id == "test_pattern"
        assert p.direction == Direction.LONG
        assert p.min_candles == 10
        assert p.frequency_pct == 5.0

    def test_detect_returns_none_with_insufficient_candles(self) -> None:
        p = ConcretePattern()
        candles = [Candle(float(i), 100.0, 101.0, 99.0, 100.0, 1000.0) for i in range(5)]
        result = p.detect(candles, [], make_regime(), make_ta())
        assert result is None

    def test_detect_returns_pattern_match(self) -> None:
        p = ConcretePattern()
        candles = [Candle(float(i), 100.0, 101.0, 99.0, 100.0, 1000.0) for i in range(15)]
        result = p.detect(candles, [], make_regime(), make_ta())
        assert result is not None
        assert result.pattern_id == "test_pattern"
        assert result.direction == Direction.LONG

    def test_check_volume_passes_when_above_threshold(self) -> None:
        p = ConcretePattern()
        candle = Candle(0.0, 100.0, 101.0, 99.0, 100.0, volume=1600.0)  # 1.6x
        ta = make_ta()  # volume_ma=1000.0
        assert p._check_volume(candle, ta, multiplier=1.5) is True

    def test_check_volume_fails_when_below_threshold(self) -> None:
        p = ConcretePattern()
        candle = Candle(0.0, 100.0, 101.0, 99.0, 100.0, volume=1400.0)  # 1.4x
        ta = make_ta()  # volume_ma=1000.0
        assert p._check_volume(candle, ta, multiplier=1.5) is False

    def test_check_close_beyond_long(self) -> None:
        p = ConcretePattern()
        candle = Candle(0.0, 99.0, 102.0, 98.0, 101.0, 1000.0)
        assert p._check_close_beyond(candle, 100.0, Direction.LONG) is True
        assert p._check_close_beyond(candle, 102.0, Direction.LONG) is False

    def test_check_close_beyond_short(self) -> None:
        p = ConcretePattern()
        candle = Candle(0.0, 101.0, 102.0, 98.0, 99.0, 1000.0)
        assert p._check_close_beyond(candle, 100.0, Direction.SHORT) is True
        assert p._check_close_beyond(candle, 98.0, Direction.SHORT) is False
