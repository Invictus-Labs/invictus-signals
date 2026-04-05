"""Market regime classifier for invictus-signals.

Implements the 33-regime hierarchy (B1-B8, BR1-BR8, C1-C8, T1-T9)
as a deterministic first-match waterfall. Config drives thresholds so
the classifier works correctly across different asset types.

Waterfall order:
  1. Check MA intermingling FIRST — chop overrides everything
  2. Check directional bullish (B1-B8)
  3. Check directional bearish (BR1-BR8)
  4. Check remaining choppy (C2-C8)
  5. Check transition (T1-T9)
  6. Fallback to T9 (exhaustion / vertical move)
"""
from __future__ import annotations

from invictus_signals.config import AssetConfig, get_config
from invictus_signals.models import (
    Direction,
    RegimeClass,
    RegimeClassification,
    RegimeId,
    TAState,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _price_between_mas(price: float, ta: TAState) -> bool:
    """True when price is sandwiched between the fast and mid MAs."""
    lo = min(ta.ma_fast, ta.ma_mid)
    hi = max(ta.ma_fast, ta.ma_mid)
    return lo < price < hi


def _mas_intermingling(ta: TAState, threshold: float) -> bool:
    """True when fast and mid MAs are very close (choppy crossover zone).

    Args:
        ta: Current TA state.
        threshold: Fractional proximity threshold from AssetConfig.
    """
    if ta.ma_mid == 0.0:
        return False
    return abs(ta.ma_fast - ta.ma_mid) / ta.ma_mid < threshold


def _make(
    regime_id: RegimeId,
    regime_class: RegimeClass,
    bias: Direction | None,
    size_multiplier: float,
    conditions_met: list[str],
    confidence: float,
) -> RegimeClassification:
    return RegimeClassification(
        regime_id=regime_id,
        regime_class=regime_class,
        bias=bias,
        size_multiplier=size_multiplier,
        conditions_met=conditions_met,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_regime(
    ta: TAState,
    current_price: float | None = None,
    config: AssetConfig | None = None,
) -> RegimeClassification:
    """Classify the current market regime from a TAState snapshot.

    Uses the first-match waterfall so the strongest signals match
    correctly and chop always wins over directional.

    Args:
        ta: TAState snapshot (output of compute_ta_state).
        current_price: Latest price. If None, uses ta.ma_fast as a
            conservative proxy.
        config: Asset configuration driving thresholds. Defaults to SPY.

    Returns:
        RegimeClassification with the matched regime, bias, and
        size multiplier.
    """
    cfg = config if config is not None else get_config("SPY")
    price = current_price if current_price is not None else ta.ma_fast
    intermingling_thresh = cfg.intermingling_threshold
    slope_flat = cfg.slope_flat_threshold

    # -----------------------------------------------------------------------
    # STEP 0 — MA intermingling (highest-priority choppy override)
    # -----------------------------------------------------------------------
    if _mas_intermingling(ta, intermingling_thresh):
        return _make(
            RegimeId.C1_COMPRESSION,
            RegimeClass.CHOPPY,
            None,
            0.25,
            [f"Fast MA and Mid MA intermingling (< {intermingling_thresh*100:.1f}% apart)"],
            0.80,
        )

    # -----------------------------------------------------------------------
    # BULLISH regimes (B1-B8)
    # -----------------------------------------------------------------------

    # B1: Bullish Trending — price > fast MA, fast slope > 0, upper BB slope > 0
    if price > ta.ma_fast and ta.ma_fast_slope > 0 and ta.bb_upper_slope > 0:
        return _make(
            RegimeId.B1_TRENDING,
            RegimeClass.BULLISH,
            Direction.LONG,
            1.0,
            ["price > fast MA", "fast MA slope > 0", "upper BB slope > 0"],
            0.90,
        )

    # B2: Bullish Continuation (golden cross + price > fast MA + upper BB slope > 0)
    if ta.ma_fast > ta.ma_mid and price > ta.ma_fast and ta.bb_upper_slope > 0:
        return _make(
            RegimeId.B2_CONTINUATION,
            RegimeClass.BULLISH,
            Direction.LONG,
            1.0,
            ["fast MA > mid MA (golden cross)", "price > fast MA", "upper BB slope > 0"],
            0.85,
        )

    # B3: Bullish Channel (price > fast MA, slope positive, not between MAs)
    if (
        price > ta.ma_fast
        and ta.ma_fast_slope > 0
        and not _price_between_mas(price, ta)
    ):
        return _make(
            RegimeId.B3_CHANNEL,
            RegimeClass.BULLISH,
            Direction.LONG,
            1.0,
            ["price > fast MA (not between MAs)", "fast MA slope > 0"],
            0.75,
        )

    # B4: Bullish Momentum (price > all MAs stacked)
    if price > ta.ma_fast and price > ta.ma_mid and price > ta.ma_slow:
        return _make(
            RegimeId.B4_MOMENTUM,
            RegimeClass.BULLISH,
            Direction.LONG,
            1.0,
            ["price > fast MA", "price > mid MA", "price > slow MA"],
            0.80,
        )

    # B5: Range-Bound Accumulation (price between fast and mid, fast rising toward mid)
    if (
        _price_between_mas(price, ta)
        and ta.ma_fast < ta.ma_mid
        and ta.ma_fast_slope > 0
    ):
        return _make(
            RegimeId.B5_ACCUMULATION,
            RegimeClass.BULLISH,
            Direction.LONG,
            0.5,
            [
                "price between fast and mid MA",
                "fast MA < mid MA (approaching cross)",
                "fast MA slope > 0",
            ],
            0.65,
        )

    # B6: Cup-and-Handle (price > fast MA, price > slow MA, macro structure intact)
    if (
        price > ta.ma_fast
        and price > ta.ma_slow
        and ta.ma_fast_slope >= 0
        and not _price_between_mas(price, ta)
    ):
        return _make(
            RegimeId.B6_CUP_HANDLE,
            RegimeClass.BULLISH,
            Direction.LONG,
            1.0,
            ["price > fast MA", "price > slow MA", "fast MA slope >= 0"],
            0.70,
        )

    # B7: Higher-Low Defense (price > mid MA, fast > mid — HL structure intact)
    if price > ta.ma_mid and ta.ma_fast > ta.ma_mid:
        return _make(
            RegimeId.B7_HL_DEFENSE,
            RegimeClass.BULLISH,
            Direction.LONG,
            0.75,
            ["price > mid MA", "fast MA > mid MA"],
            0.65,
        )

    # B8: Bullish Reversal from Oversold
    if (
        price < ta.bb_lower
        and ta.bb_upper_slope >= 0
        and ta.ma_fast_slope >= 0
    ):
        return _make(
            RegimeId.B8_REVERSAL_OVERSOLD,
            RegimeClass.BULLISH,
            Direction.LONG,
            0.5,
            [
                "price < lower BB",
                "upper BB slope >= 0",
                "fast slope >= 0 (not confirmed downtrend)",
            ],
            0.55,
        )

    # -----------------------------------------------------------------------
    # BEARISH regimes (BR1-BR8)
    # -----------------------------------------------------------------------

    # BR1: Aggressive Downtrend (fast < mid, price < slow, BB slope < 0)
    if ta.ma_fast < ta.ma_mid and price < ta.ma_slow and ta.bb_upper_slope < 0:
        return _make(
            RegimeId.BR1_AGGRESSIVE,
            RegimeClass.BEARISH,
            Direction.SHORT,
            1.0,
            ["fast MA < mid MA", "price < slow MA", "BB slope < 0"],
            0.90,
        )

    # BR2: Bearish Trend Continuation
    if ta.ma_fast < ta.ma_mid and price < ta.ma_fast and ta.ma_fast_slope < 0:
        return _make(
            RegimeId.BR2_CONTINUATION,
            RegimeClass.BEARISH,
            Direction.SHORT,
            1.0,
            ["fast MA < mid MA", "price < fast MA", "fast MA slope < 0"],
            0.85,
        )

    # BR3: High-Momentum Downtrend
    if price < ta.ma_fast and price < ta.ma_mid and ta.ma_fast_slope < 0:
        return _make(
            RegimeId.BR3_HIGH_MOMENTUM,
            RegimeClass.BEARISH,
            Direction.SHORT,
            1.0,
            ["price < fast MA", "price < mid MA", "fast slope < 0"],
            0.80,
        )

    # BR4: Macro Downtrend (all MAs overhead)
    if price < ta.ma_fast and price < ta.ma_mid and price < ta.ma_slow:
        return _make(
            RegimeId.BR4_MACRO,
            RegimeClass.BEARISH,
            Direction.SHORT,
            1.0,
            ["price < fast MA", "price < mid MA", "price < slow MA"],
            0.85,
        )

    # BR5: Bearish Continuation / Slope Confirm
    if price < ta.ma_fast and ta.ma_fast_slope < 0:
        return _make(
            RegimeId.BR5_SLOPE_CONFIRM,
            RegimeClass.BEARISH,
            Direction.SHORT,
            0.75,
            ["price < fast MA", "fast MA slope < 0"],
            0.75,
        )

    # BR6: Technical Bear Market
    if price < ta.ma_fast and ta.bb_upper_slope < -0.05:
        return _make(
            RegimeId.BR6_TECHNICAL,
            RegimeClass.BEARISH,
            Direction.SHORT,
            0.75,
            ["price < fast MA", "BB upper slope < -0.05"],
            0.70,
        )

    # BR7: Fear-Driven Selloff
    if price < ta.bb_middle and price < ta.ma_mid and ta.ma_fast_slope < 0:
        return _make(
            RegimeId.BR7_FEAR_DRIVEN,
            RegimeClass.BEARISH,
            Direction.SHORT,
            0.5,
            ["price < BB middle", "price < mid MA", "fast slope < 0"],
            0.65,
        )

    # BR8: Inverse Cup Formation
    if price < ta.ma_fast and ta.ma_fast < ta.ma_mid:
        return _make(
            RegimeId.BR8_INVERSE_CUP,
            RegimeClass.BEARISH,
            Direction.SHORT,
            0.5,
            ["price < fast MA", "fast MA < mid MA (death cross)"],
            0.60,
        )

    # -----------------------------------------------------------------------
    # CHOPPY regimes (C2-C8)  [C1 handled above]
    # -----------------------------------------------------------------------

    # C2: Congested Zone
    if price > ta.ma_fast and price < ta.ma_mid:
        return _make(
            RegimeId.C2_RANGE,
            RegimeClass.CHOPPY,
            None,
            0.25,
            ["price > fast MA", "price < mid MA (congested zone)"],
            0.70,
        )

    # C3: Flat MAs with price between them
    if (
        _price_between_mas(price, ta)
        and abs(ta.ma_fast_slope) < slope_flat
        and abs(ta.ma_mid_slope) < slope_flat
    ):
        return _make(
            RegimeId.C3_FLAG,
            RegimeClass.CHOPPY,
            None,
            0.25,
            ["price between fast and mid MA", "fast slope ~0", "mid slope ~0"],
            0.65,
        )

    # C4: Catalyst-Pending (MAs converging within 0.5%)
    if ta.ma_mid != 0.0 and abs(ta.ma_fast - ta.ma_mid) / ta.ma_mid < 0.005:
        return _make(
            RegimeId.C4_VOLATILITY,
            RegimeClass.CHOPPY,
            None,
            0.25,
            ["fast MA and mid MA converging (< 0.5% apart)"],
            0.70,
        )

    # C5: Indecisive Range — price oscillating around VWAP
    if ta.vwap != 0 and abs(price - ta.vwap) / ta.vwap < 0.001:
        return _make(
            RegimeId.C5_INSIDE_BAR,
            RegimeClass.CHOPPY,
            None,
            0.25,
            ["price within 0.1% of VWAP"],
            0.60,
        )

    # C6: Inside Day Compression — BBs squeezing
    if ta.bb_width < 0.01:
        return _make(
            RegimeId.C6_SQUEEZE,
            RegimeClass.CHOPPY,
            None,
            0.25,
            ["BB width < 1% (squeeze compression)"],
            0.65,
        )

    # C7: Low-Volatility Pre-Catalyst
    if abs(ta.ma_fast_slope) < slope_flat * 0.5 and ta.bb_width < 0.02:
        return _make(
            RegimeId.C7_OSCILLATION,
            RegimeClass.CHOPPY,
            None,
            0.25,
            ["fast MA slope ~0", "BB width < 2%"],
            0.60,
        )

    # C8: Flagging Structure — price within BB with minimal slope
    if ta.bb_lower < price < ta.bb_upper and abs(ta.ma_fast_slope) < slope_flat * 2:
        return _make(
            RegimeId.C8_DRIFT,
            RegimeClass.CHOPPY,
            None,
            0.25,
            ["price within BB", "fast slope near-flat"],
            0.55,
        )

    # -----------------------------------------------------------------------
    # TRANSITION regimes (T1-T9)
    # -----------------------------------------------------------------------

    # T1: Mean Reversion from Oversold
    if price < ta.bb_lower:
        return _make(
            RegimeId.T1_MEAN_REVERSION,
            RegimeClass.TRANSITION,
            Direction.LONG,
            0.5,
            ["price < lower BB (mean-reversion rally probable)"],
            0.65,
        )

    # T2: Mean Reversion from Overbought
    if price > ta.bb_upper and ta.bb_upper_slope < 0:
        return _make(
            RegimeId.T2_MA_CROSSOVER,
            RegimeClass.TRANSITION,
            Direction.SHORT,
            0.5,
            ["price > upper BB", "BB upper slope < 0 (overbought reversal)"],
            0.65,
        )

    # T3: Bull Reversal — fast crossing above mid after downtrend
    if ta.ma_fast >= ta.ma_mid and ta.ma_fast_slope > 0 and price > ta.ma_mid:
        return _make(
            RegimeId.T3_BULL_REVERSAL,
            RegimeClass.TRANSITION,
            Direction.LONG,
            0.75,
            [
                "fast MA >= mid MA (golden cross forming)",
                "fast MA slope > 0",
                "price > mid MA",
            ],
            0.70,
        )

    # T4: Fast MA Plateau Reclaim
    if (
        price > ta.ma_fast
        and abs(ta.ma_fast_slope) < slope_flat
        and ta.ma_fast < ta.ma_mid
    ):
        return _make(
            RegimeId.T4_PLATEAU_RECLAIM,
            RegimeClass.TRANSITION,
            Direction.LONG,
            0.5,
            [
                "price > fast MA",
                "fast MA slope flat (plateau)",
                "fast MA < mid MA (not yet crossed)",
            ],
            0.60,
        )

    # T5: Bullish-to-Bearish Channel Break
    if price < ta.ma_fast and ta.ma_fast_slope < 0 and price > ta.ma_mid:
        return _make(
            RegimeId.T5_BEAR_REVERSAL,
            RegimeClass.TRANSITION,
            Direction.SHORT,
            0.5,
            [
                "price < fast MA",
                "fast MA slope < 0",
                "price still > mid MA (early breakdown)",
            ],
            0.60,
        )

    # T6: Higher-Low Breach
    if price < ta.ma_mid and ta.ma_fast_slope < 0:
        return _make(
            RegimeId.T6_HL_BREACH,
            RegimeClass.TRANSITION,
            Direction.SHORT,
            0.5,
            ["price < mid MA", "fast MA slope < 0 (HL structure breach)"],
            0.60,
        )

    # T7: Reversal Structure (price approaching fast MA from below)
    if (
        price < ta.ma_fast
        and ta.ma_fast != 0.0
        and (ta.ma_fast - price) / ta.ma_fast < 0.005
        and ta.ma_fast_slope >= 0
    ):
        return _make(
            RegimeId.T7_CHANNEL_BREAK,
            RegimeClass.TRANSITION,
            Direction.LONG,
            0.5,
            [
                "price just below fast MA (< 0.5% away)",
                "fast MA slope >= 0 (reversal structure forming)",
            ],
            0.55,
        )

    # T8: Post-Bounce Confirmation
    if price > ta.bb_lower and ta.bb_upper_slope > 0 and ta.ma_fast_slope >= 0:
        return _make(
            RegimeId.T8_POST_BOUNCE,
            RegimeClass.TRANSITION,
            Direction.LONG,
            0.5,
            [
                "price > lower BB (post-bounce)",
                "BB upper slope > 0",
                "fast MA slope >= 0",
            ],
            0.55,
        )

    # T9: Vertical Move / Exhaustion — catch-all
    return _make(
        RegimeId.T9_EXHAUSTION,
        RegimeClass.TRANSITION,
        None,
        0.25,
        ["No primary regime conditions met (potential exhaustion / vertical move)"],
        0.40,
    )
