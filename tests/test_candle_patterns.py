"""Tests for invictus_signals.candle_patterns."""
from __future__ import annotations

import pytest

from invictus_signals.candle_patterns import (
    detect_candlestick_patterns,
    is_bearish_engulfing,
    is_bullish_engulfing,
    is_doji,
    is_hammer,
    is_inverted_hammer,
)
from invictus_signals.models import Candle


def candle(
    open_: float,
    high: float,
    low: float,
    close: float,
    timestamp: float = 0.0,
    volume: float = 1000.0,
) -> Candle:
    return Candle(timestamp=timestamp, open=open_, high=high, low=low, close=close, volume=volume)


class TestIsHammer:
    def test_classic_hammer(self) -> None:
        # Small body at top, long lower wick
        c = candle(open_=100.0, high=100.5, low=95.0, close=100.2)
        assert is_hammer(c) is True

    def test_not_hammer_large_body(self) -> None:
        # Large body relative to range
        c = candle(open_=95.0, high=105.0, low=94.0, close=105.0)
        assert is_hammer(c) is False

    def test_not_hammer_no_lower_wick(self) -> None:
        # Long upper wick, short lower wick — inverted hammer
        c = candle(open_=100.0, high=107.0, low=99.8, close=100.2)
        assert is_hammer(c) is False

    def test_doji_range_zero(self) -> None:
        # All OHLC same — degenerate candle
        c = candle(open_=100.0, high=100.0, low=100.0, close=100.0)
        assert is_hammer(c) is False

    def test_hammer_bearish_color(self) -> None:
        # Hammer can be either bullish or bearish
        c = candle(open_=100.2, high=100.5, low=95.0, close=100.0)
        assert is_hammer(c) is True


class TestIsInvertedHammer:
    def test_classic_inverted_hammer(self) -> None:
        # Small body at bottom, long upper wick
        c = candle(open_=100.0, high=106.0, low=99.8, close=100.2)
        assert is_inverted_hammer(c) is True

    def test_not_inverted_hammer_large_body(self) -> None:
        c = candle(open_=95.0, high=110.0, low=94.0, close=108.0)
        assert is_inverted_hammer(c) is False

    def test_not_inverted_when_lower_wick_dominates(self) -> None:
        # Lower wick > upper wick → hammer, not inverted
        c = candle(open_=100.0, high=100.5, low=94.0, close=100.2)
        assert is_inverted_hammer(c) is False


class TestIsDoji:
    def test_perfect_doji(self) -> None:
        # Open = close
        c = candle(open_=100.0, high=103.0, low=97.0, close=100.0)
        assert is_doji(c) is True

    def test_nearly_doji(self) -> None:
        # Very small body (0.1% of range)
        c = candle(open_=100.0, high=103.0, low=97.0, close=100.05)
        # Body = 0.05, range = 6.0 → ratio = 0.0083 → doji
        assert is_doji(c) is True

    def test_not_doji_large_body(self) -> None:
        c = candle(open_=95.0, high=105.0, low=94.0, close=103.0)
        assert is_doji(c) is False

    def test_zero_range_is_doji(self) -> None:
        c = candle(open_=100.0, high=100.0, low=100.0, close=100.0)
        assert is_doji(c) is True

    def test_custom_ratio(self) -> None:
        # With stricter 2% ratio
        c = candle(open_=100.0, high=103.0, low=97.0, close=100.1)
        # Body = 0.1, range = 6.0 → ratio = 0.0167 → not doji at 1%
        assert is_doji(c, body_ratio=0.01) is False
        assert is_doji(c, body_ratio=0.05) is True


class TestIsBullishEngulfing:
    def test_classic_bullish_engulfing(self) -> None:
        prev = candle(open_=102.0, high=102.5, low=99.0, close=99.5)  # Bearish
        curr = candle(open_=99.0, high=104.0, low=98.5, close=103.5)  # Bullish engulfs
        assert is_bullish_engulfing(prev, curr) is True

    def test_not_bullish_when_prev_bullish(self) -> None:
        prev = candle(open_=99.0, high=103.0, low=98.0, close=102.0)  # Bullish prev
        curr = candle(open_=99.0, high=104.0, low=98.5, close=103.5)  # Bullish curr
        assert is_bullish_engulfing(prev, curr) is False

    def test_not_bullish_when_curr_bearish(self) -> None:
        prev = candle(open_=102.0, high=102.5, low=99.0, close=99.5)  # Bearish
        curr = candle(open_=103.0, high=104.0, low=98.5, close=99.0)  # Bearish curr
        assert is_bullish_engulfing(prev, curr) is False

    def test_partial_engulf_not_triggered(self) -> None:
        prev = candle(open_=102.0, high=102.5, low=99.0, close=99.5)  # Bearish, body 99.5-102.0
        curr = candle(open_=100.0, high=103.0, low=99.5, close=102.5)  # Doesn't engulf prev open
        # curr.close=102.5 >= prev.open=102.0 ✓ but curr.open=100.0 > prev.close=99.5 ✗
        assert is_bullish_engulfing(prev, curr) is False


class TestIsBearishEngulfing:
    def test_classic_bearish_engulfing(self) -> None:
        prev = candle(open_=99.0, high=103.0, low=98.5, close=102.5)  # Bullish
        curr = candle(open_=103.0, high=103.5, low=97.0, close=98.0)  # Bearish engulfs
        assert is_bearish_engulfing(prev, curr) is True

    def test_not_bearish_when_prev_bearish(self) -> None:
        prev = candle(open_=103.0, high=103.5, low=99.0, close=100.0)  # Bearish prev
        curr = candle(open_=103.0, high=103.5, low=97.0, close=98.0)  # Bearish curr
        assert is_bearish_engulfing(prev, curr) is False

    def test_not_bearish_when_curr_bullish(self) -> None:
        prev = candle(open_=99.0, high=103.0, low=98.5, close=102.5)  # Bullish
        curr = candle(open_=100.0, high=105.0, low=99.0, close=104.0)  # Bullish curr
        assert is_bearish_engulfing(prev, curr) is False


class TestDetectCandlestickPatterns:
    def test_returns_list(self) -> None:
        candles = [
            candle(100.0, 100.5, 94.0, 100.2, timestamp=0.0),  # Hammer
            candle(100.2, 100.3, 100.0, 100.1, timestamp=1.0),  # Potential doji
        ]
        result = detect_candlestick_patterns(candles)
        assert isinstance(result, list)

    def test_detects_hammer(self) -> None:
        hammer_candle = candle(100.0, 100.5, 94.0, 100.2, timestamp=0.0)
        result = detect_candlestick_patterns([hammer_candle])
        pattern_names = [r["pattern"] for r in result]
        assert "hammer" in pattern_names

    def test_detects_doji(self) -> None:
        doji_candle = candle(100.0, 103.0, 97.0, 100.0, timestamp=0.0)
        result = detect_candlestick_patterns([doji_candle])
        pattern_names = [r["pattern"] for r in result]
        assert "doji" in pattern_names

    def test_detects_engulfing_two_candles(self) -> None:
        prev = candle(102.0, 102.5, 99.0, 99.5, timestamp=0.0)  # Bearish
        curr = candle(99.0, 104.0, 98.5, 103.5, timestamp=1.0)   # Bullish engulfing
        result = detect_candlestick_patterns([prev, curr])
        pattern_names = [r["pattern"] for r in result]
        assert "bullish_engulfing" in pattern_names

    def test_empty_candles_returns_empty(self) -> None:
        result = detect_candlestick_patterns([])
        assert result == []

    def test_single_candle_no_engulfing(self) -> None:
        c = candle(100.0, 100.5, 94.0, 100.2)
        result = detect_candlestick_patterns([c])
        pattern_names = [r["pattern"] for r in result]
        assert "bullish_engulfing" not in pattern_names
        assert "bearish_engulfing" not in pattern_names

    def test_result_has_required_keys(self) -> None:
        c = candle(100.0, 103.0, 97.0, 100.0)  # Doji
        result = detect_candlestick_patterns([c])
        assert len(result) > 0
        for r in result:
            assert "pattern" in r
            assert "bar_index" in r
            assert "timestamp" in r
            assert "candle" in r
