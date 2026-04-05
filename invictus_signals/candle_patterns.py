"""Candlestick pattern detection for invictus-signals.

Implements common single and multi-candle patterns on any OHLCV data.
All functions are pure and deterministic — no I/O, no side effects.

Patterns implemented:
  - Hammer (bullish reversal at support)
  - Inverted Hammer (bullish reversal potential)
  - Doji (indecision)
  - Bullish Engulfing
  - Bearish Engulfing
"""
from __future__ import annotations

from invictus_signals.models import Candle


# ---------------------------------------------------------------------------
# Single-candle body / wick helpers
# ---------------------------------------------------------------------------


def _body_size(c: Candle) -> float:
    """Absolute distance between open and close."""
    return abs(c.close - c.open)


def _upper_wick(c: Candle) -> float:
    """Length of the upper wick."""
    return c.high - max(c.open, c.close)


def _lower_wick(c: Candle) -> float:
    """Length of the lower wick."""
    return min(c.open, c.close) - c.low


def _total_range(c: Candle) -> float:
    """Total high-to-low range."""
    return c.high - c.low


def _is_bullish(c: Candle) -> bool:
    """True when close > open."""
    return c.close > c.open


def _is_bearish(c: Candle) -> bool:
    """True when close < open."""
    return c.close < c.open


# ---------------------------------------------------------------------------
# Pattern detection functions
# ---------------------------------------------------------------------------


def is_hammer(
    candle: Candle,
    body_ratio: float = 0.33,
    wick_ratio: float = 2.0,
) -> bool:
    """Detect a Hammer candlestick pattern (bullish reversal at support).

    Conditions:
    - Small body in the upper third of the total range
    - Lower wick >= wick_ratio × body size
    - Upper wick <= body size (tiny or absent upper wick)
    - Total range must be non-zero

    Args:
        candle: The candle to evaluate.
        body_ratio: Max body as fraction of total range (default 0.33).
        wick_ratio: Min lower wick vs body multiplier (default 2.0).

    Returns:
        True if hammer pattern detected.
    """
    total = _total_range(candle)
    if total == 0.0:
        return False

    body = _body_size(candle)
    lower = _lower_wick(candle)
    upper = _upper_wick(candle)

    # Body is small relative to total range
    if body / total > body_ratio:
        return False

    # Lower wick is at least wick_ratio × body
    min_body = body if body > 0 else total * 0.01
    if lower < wick_ratio * min_body:
        return False

    # Upper wick is tiny (not bigger than body)
    if upper > body and upper > total * 0.1:
        return False

    return True


def is_inverted_hammer(
    candle: Candle,
    body_ratio: float = 0.33,
    wick_ratio: float = 2.0,
) -> bool:
    """Detect an Inverted Hammer candlestick (bullish reversal potential).

    Conditions:
    - Small body in the lower third of the total range
    - Upper wick >= wick_ratio × body size
    - Lower wick <= body size (tiny or absent lower wick)

    Args:
        candle: The candle to evaluate.
        body_ratio: Max body as fraction of total range (default 0.33).
        wick_ratio: Min upper wick vs body multiplier (default 2.0).

    Returns:
        True if inverted hammer pattern detected.
    """
    total = _total_range(candle)
    if total == 0.0:
        return False

    body = _body_size(candle)
    upper = _upper_wick(candle)
    lower = _lower_wick(candle)

    if body / total > body_ratio:
        return False

    min_body = body if body > 0 else total * 0.01
    if upper < wick_ratio * min_body:
        return False

    if lower > body and lower > total * 0.1:
        return False

    return True


def is_doji(
    candle: Candle,
    body_ratio: float = 0.05,
) -> bool:
    """Detect a Doji candlestick (market indecision).

    A doji has an extremely small body relative to total range —
    open and close are virtually equal.

    Args:
        candle: The candle to evaluate.
        body_ratio: Max body as fraction of total range (default 0.05 = 5%).

    Returns:
        True if doji pattern detected.
    """
    total = _total_range(candle)
    if total == 0.0:
        # Perfect doji — open == high == low == close
        return True

    body = _body_size(candle)
    return body / total <= body_ratio


def is_bullish_engulfing(
    prev: Candle,
    curr: Candle,
) -> bool:
    """Detect a Bullish Engulfing pattern (two-candle reversal).

    Conditions:
    - Prior candle is bearish (close < open)
    - Current candle is bullish (close > open)
    - Current body completely engulfs prior body
      (curr.open <= prev.close AND curr.close >= prev.open)

    Args:
        prev: The previous candle.
        curr: The current candle.

    Returns:
        True if bullish engulfing pattern detected.
    """
    if not _is_bearish(prev):
        return False
    if not _is_bullish(curr):
        return False
    # Current body must engulf prior body
    return curr.open <= prev.close and curr.close >= prev.open


def is_bearish_engulfing(
    prev: Candle,
    curr: Candle,
) -> bool:
    """Detect a Bearish Engulfing pattern (two-candle reversal).

    Conditions:
    - Prior candle is bullish (close > open)
    - Current candle is bearish (close < open)
    - Current body completely engulfs prior body
      (curr.open >= prev.close AND curr.close <= prev.open)

    Args:
        prev: The previous candle.
        curr: The current candle.

    Returns:
        True if bearish engulfing pattern detected.
    """
    if not _is_bullish(prev):
        return False
    if not _is_bearish(curr):
        return False
    return curr.open >= prev.close and curr.close <= prev.open


# ---------------------------------------------------------------------------
# Batch detection
# ---------------------------------------------------------------------------


def detect_candlestick_patterns(
    candles: list[Candle],
) -> list[dict[str, object]]:
    """Detect all candlestick patterns in a candle list.

    Scans for single-candle patterns on every bar and two-candle
    patterns on every pair of consecutive bars.

    Args:
        candles: List of candles (oldest first).

    Returns:
        List of dicts with keys: pattern, bar_index, timestamp, candle.
    """
    results: list[dict[str, object]] = []

    for i, c in enumerate(candles):
        if is_hammer(c):
            results.append({
                "pattern": "hammer",
                "bar_index": i,
                "timestamp": c.timestamp,
                "candle": c,
            })
        if is_inverted_hammer(c):
            results.append({
                "pattern": "inverted_hammer",
                "bar_index": i,
                "timestamp": c.timestamp,
                "candle": c,
            })
        if is_doji(c):
            results.append({
                "pattern": "doji",
                "bar_index": i,
                "timestamp": c.timestamp,
                "candle": c,
            })

        if i > 0:
            prev = candles[i - 1]
            if is_bullish_engulfing(prev, c):
                results.append({
                    "pattern": "bullish_engulfing",
                    "bar_index": i,
                    "timestamp": c.timestamp,
                    "candle": c,
                })
            if is_bearish_engulfing(prev, c):
                results.append({
                    "pattern": "bearish_engulfing",
                    "bar_index": i,
                    "timestamp": c.timestamp,
                    "candle": c,
                })

    return results
