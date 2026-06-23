"""Universal Do-Not-Trade filters for invictus-signals.

Implements 13+ asset-agnostic DNT filters. SPY-specific filters
(opening trap, VWAP EOD, IV/theta, mobile) are excluded. Filter 07
uses a percentage-based chase threshold from AssetConfig instead of
absolute SPY points.

All logic is deterministic — no I/O, no side effects.
"""
from __future__ import annotations

from typing import Sequence

from invictus_signals.config import AssetConfig, get_config
from invictus_signals.models import (
    AlgoLine,
    Candle,
    DNTResult,
    Direction,
    RegimeClass,
    RegimeClassification,
    TAState,
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _make_result(
    filter_id: str,
    name: str,
    triggered: bool,
    reason: str,
    frequency_pct: float,
) -> DNTResult:
    return DNTResult(
        filter_id=filter_id,
        name=name,
        triggered=triggered,
        reason=reason,
        frequency_pct=frequency_pct,
    )


def _count_alternating_swings(candles: Sequence[Candle]) -> int:
    """Count consecutive alternating swing highs/lows."""
    if len(candles) < 3:
        return 0
    swings: list[str] = []
    for i in range(1, len(candles) - 1):
        prev_h, cur_h, next_h = candles[i - 1].high, candles[i].high, candles[i + 1].high
        prev_l, cur_l, next_l = candles[i - 1].low, candles[i].low, candles[i + 1].low
        if cur_h > prev_h and cur_h > next_h:
            swings.append("H")
        elif cur_l < prev_l and cur_l < next_l:
            swings.append("L")

    count = 0
    for i in range(1, len(swings)):
        if swings[i] != swings[i - 1]:
            count += 1
    return count


def _range_last_n_candles(candles: Sequence[Candle], n: int) -> float:
    """High-low range of the last n candles."""
    window = list(candles[-n:]) if len(candles) >= n else list(candles)
    if not window:
        return 0.0
    return max(c.high for c in window) - min(c.low for c in window)


# ---------------------------------------------------------------------------
# Individual DNT filters
# ---------------------------------------------------------------------------


def dnt_01_no_structure(lines: Sequence[AlgoLine]) -> DNTResult:
    """DNT 01: No clear algorithmic structure.

    Triggered when fewer than 2 lines have 2+ touch points.
    """
    qualified = [ln for ln in lines if len(ln.touch_points) >= 2]
    triggered = len(qualified) < 2
    return _make_result(
        "dnt_01_no_structure",
        "No Clear Algorithmic Structure",
        triggered,
        (
            f"Only {len(qualified)} line(s) with 2+ touches (need 2+)"
            if triggered
            else f"{len(qualified)} qualified lines found"
        ),
        67.2,
    )


def dnt_02_choppy(
    candles: Sequence[Candle],
    choppy_range_threshold: float = 1.0,
) -> DNTResult:
    """DNT 02: Choppy / sideways / range-bound price action.

    Triggered when 4+ alternating swings are detected in recent candles,
    OR when the 60-bar range is below the config threshold.

    Args:
        candles: Candle series.
        choppy_range_threshold: Minimum range to not trigger (from config).
    """
    recent = list(candles[-60:]) if len(candles) >= 60 else list(candles)
    swings = _count_alternating_swings(recent)
    range_60 = _range_last_n_candles(candles, 60)

    triggered = swings >= 4 or range_60 < choppy_range_threshold
    reason = (
        f"Alternating swings={swings} (>= 4) OR range={range_60:.4f} (< {choppy_range_threshold})"
        if triggered
        else f"Swings={swings}, range={range_60:.4f} — not choppy"
    )
    return _make_result(
        "dnt_02_choppy",
        "Choppy / Sideways / Range-Bound",
        triggered,
        reason,
        62.7,
    )


def dnt_03_no_breakout_confirmation(
    candles: Sequence[Candle],
    trigger_level: float,
    direction: Direction,
) -> DNTResult:
    """DNT 03: No breakout confirmation (< 2 consecutive closes beyond trigger)."""
    recent = list(candles[-5:]) if len(candles) >= 5 else list(candles)
    consecutive = 0
    best = 0
    for c in recent:
        if direction == Direction.LONG and c.close > trigger_level:
            consecutive += 1
        elif direction == Direction.SHORT and c.close < trigger_level:
            consecutive += 1
        else:
            consecutive = 0
        best = max(best, consecutive)

    triggered = best < 2
    return _make_result(
        "dnt_03_no_breakout_confirmation",
        "No Breakout Confirmation",
        triggered,
        (
            f"Only {best} consecutive close(s) beyond trigger {trigger_level:.4f} (need 2)"
            if triggered
            else f"{best} consecutive closes confirmed breakout"
        ),
        3.0,
    )


def dnt_04_inside_wedge(
    candles: Sequence[Candle],
    wedge_upper: float,
    wedge_lower: float,
) -> DNTResult:
    """DNT 04: Inside a converging wedge / tapering structure."""
    recent = list(candles[-5:]) if len(candles) >= 5 else list(candles)
    has_closed_outside = any(
        c.close > wedge_upper or c.close < wedge_lower for c in recent
    )
    current_inside = (
        candles[-1].close <= wedge_upper and candles[-1].close >= wedge_lower
        if candles
        else True
    )
    triggered = current_inside and not has_closed_outside
    return _make_result(
        "dnt_04_inside_wedge",
        "Inside Converging Wedge / Tapering Structure",
        triggered,
        (
            f"Price inside wedge [{wedge_lower:.4f}, {wedge_upper:.4f}] — no close outside"
            if triggered
            else "Price has closed outside wedge boundary"
        ),
        22.9,
    )


def dnt_05_trapped_between_mas(
    current_price: float,
    ta: TAState,
) -> DNTResult:
    """DNT 05: Price trapped between fast and mid moving averages."""
    lo = min(ta.ma_fast, ta.ma_mid)
    hi = max(ta.ma_fast, ta.ma_mid)
    triggered = lo < current_price < hi
    return _make_result(
        "dnt_05_trapped_between_mas",
        "Price Trapped Between Moving Averages",
        triggered,
        (
            f"Price {current_price:.4f} trapped between fast MA={ta.ma_fast:.4f} "
            f"and mid MA={ta.ma_mid:.4f}"
            if triggered
            else f"Price {current_price:.4f} not between MAs ({lo:.4f}–{hi:.4f})"
        ),
        22.8,
    )


def dnt_06_no_short_uptrend(
    ta: TAState,
    intended_direction: Direction,
    regime_class: RegimeClass | None = None,
    *,
    regime_bias: Direction | None = None,
) -> DNTResult:
    """DNT 06: Do not short in an active uptrend.

    Triggered when intended direction is SHORT and ANY of:
      - The fast MA slope is positive (original slope gate).
      - The regime class is BULLISH (b7/b8 pullback fix, 2026-06-13).
      - The regime bias is LONG in a TRANSITION regime — blocks shorts in
        bullish-leaning transitions (T3_BULL_REVERSAL, T8_POST_BOUNCE) that
        carry ``bias=LONG`` but ``regime_class=TRANSITION``.  Without this,
        a T3/T8 short slips through the BULLISH equality check even though
        the market is clearly bias-long. (E4, alpha-wave1.)

    All three inputs are optional beyond ``ta`` and ``intended_direction``;
    omitting them preserves byte-identical behaviour to prior releases.
    """
    if intended_direction != Direction.SHORT:
        return _make_result(
            "dnt_06_no_short_uptrend",
            "Do Not Short in Active Uptrend",
            False,
            "Not a short trade — filter not applicable",
            14.9,
        )
    slope_up = ta.ma_fast_slope > 0
    bullish_regime = regime_class == RegimeClass.BULLISH
    # Block shorts when regime class is TRANSITION but bias is LONG (e.g. T3/T8).
    # When regime_bias is None the check is False — full back-compat.
    transition_long_bias = (
        regime_class == RegimeClass.TRANSITION and regime_bias == Direction.LONG
    )
    triggered = slope_up or bullish_regime or transition_long_bias
    if slope_up:
        detail = (
            f"Fast MA slope={ta.ma_fast_slope:.4f} > 0 — uptrend intact, no shorting"
        )
    elif bullish_regime:
        detail = (
            f"Regime BULLISH (price/MA structure up) with flat slope "
            f"({ta.ma_fast_slope:.4f}) — no shorting into a confirmed uptrend"
        )
    elif transition_long_bias:
        detail = (
            f"Regime TRANSITION with bias=LONG (slope={ta.ma_fast_slope:.4f}) "
            f"— bullish-leaning reversal, no shorting"
        )
    else:
        detail = (
            f"Fast MA slope={ta.ma_fast_slope:.4f} <= 0 and regime not bullish "
            f"— shorting allowed"
        )
    return _make_result(
        "dnt_06_no_short_uptrend",
        "Do Not Short in Active Uptrend",
        triggered,
        detail,
        14.9,
    )


def dnt_14_weak_intraday_trend(
    ta: TAState,
    min_intraday_adx: float = 30.0,
) -> DNTResult:
    """DNT 14: Veto entries when the entry-timeframe (1H) trend is too weak.

    Momentum/breakout patterns (LB, SD, FB, ...) only have edge when the 1H is
    genuinely trending; in 1H chop they get faded in BOTH directions. Keyed off
    ``ta.intraday_adx`` (ADX on the intraday bars), NOT the daily ``ta.adx`` — a
    trending daily can sit on a choppy 1H, and daily ADX is empirically inverted
    vs trade outcomes (winners ~46 / losers ~26 on the 1H; the reverse on daily).

    ``intraday_adx <= 0`` is the "no intraday data" sentinel and fails OPEN (does
    not trigger) so warmup TAStates behave exactly as before.

    Args:
        ta: Current TA state (must carry ``intraday_adx``).
        min_intraday_adx: Minimum 1H ADX to permit a momentum entry.
    """
    adx = ta.intraday_adx
    triggered = 0.0 < adx < min_intraday_adx
    return _make_result(
        "dnt_14_weak_intraday_trend",
        "Weak Intraday Trend (Chop Guard)",
        triggered,
        (
            f"1H ADX {adx:.1f} < {min_intraday_adx:.1f} — choppy entry timeframe; "
            "momentum entries get faded"
            if triggered
            else f"1H ADX {adx:.1f} >= {min_intraday_adx:.1f} (or absent) — entry trend OK"
        ),
        0.0,
    )


def dnt_07_chasing_missed_entry(
    current_price: float,
    trigger_level: float,
    direction: Direction,
    chase_threshold_pct: float = 0.001,
) -> DNTResult:
    """DNT 07: Do not chase a missed entry.

    Triggered when price has moved more than chase_threshold_pct beyond
    the trigger level without a retest. Uses percentage-based threshold
    to work correctly across all asset prices.

    Args:
        current_price: Latest market price.
        trigger_level: The entry trigger price.
        direction: Trade direction.
        chase_threshold_pct: Maximum overshoot as fraction of trigger price.
    """
    if direction == Direction.LONG:
        overshoot = current_price - trigger_level
    else:
        overshoot = trigger_level - current_price

    chase_threshold = trigger_level * chase_threshold_pct
    triggered = overshoot > chase_threshold
    return _make_result(
        "dnt_07_chasing_missed_entry",
        "Do Not Chase a Missed Entry",
        triggered,
        (
            f"Price moved {overshoot:.4f} beyond trigger {trigger_level:.4f} "
            f"(threshold {chase_threshold:.4f}) — chasing"
            if triggered
            else f"Overshoot {overshoot:.4f} <= {chase_threshold:.4f} — entry still valid"
        ),
        14.5,
    )


def dnt_08_overtrading(
    trade_count: int,
    max_trades: int = 3,
) -> DNTResult:
    """DNT 08: Overtrading limit."""
    triggered = trade_count >= max_trades
    return _make_result(
        "dnt_08_overtrading",
        "Overtrading Limit",
        triggered,
        (
            f"Trade count={trade_count} >= max={max_trades} — stop trading"
            if triggered
            else f"Trade count={trade_count} < {max_trades} — may continue"
        ),
        11.9,
    )


def dnt_09_buying_downtrend(
    ta: TAState,
    current_price: float,
    intended_direction: Direction,
    *,
    regime_class: RegimeClass | None = None,
    regime_bias: Direction | None = None,
) -> DNTResult:
    """DNT 09: Do not buy in a downtrend / catch falling knives.

    Daily knife: fast (daily) slope is negative AND price is below the daily
    mid MA. That condition alone holds for days-to-weeks after a multi-day
    dump — long after the knife has stopped falling — so it is released when
    the intraday structure has demonstrably turned: price above the intraday
    fast MA with a positive intraday close slope (2026-06-06/07 incident:
    530 consecutive LONG blocks across BTC/ETH/SOL/BNB through a V-recovery
    that was already above every 1h MA).

    A TAState without intraday data (intraday_ma_fast == 0.0 sentinel) keeps
    the original daily-only behavior — the release never applies.

    E4 — TRANSITION-regime bias coupling: also block longs when the regime
    class is TRANSITION with ``bias=SHORT`` (bearish-leaning transitions
    T5_BEAR_REVERSAL / T6_HL_BREACH that carry ``bias=SHORT`` but
    ``regime_class=TRANSITION``).  Mirrors the dnt_06 extension symmetrically.
    Both ``regime_class`` and ``regime_bias`` default to None — full
    back-compat when omitted.
    """
    if intended_direction != Direction.LONG:
        return _make_result(
            "dnt_09_buying_downtrend",
            "Do Not Buy in Downtrend / Catch Falling Knife",
            False,
            "Not a long trade — filter not applicable",
            11.1,
        )
    daily_knife = ta.ma_fast_slope < 0 and current_price < ta.ma_mid
    intraday_recovery = (
        ta.intraday_ma_fast > 0.0
        and current_price > ta.intraday_ma_fast
        and ta.intraday_close_slope > 0
    )
    # Block longs when regime class is TRANSITION but bias is SHORT (e.g. T5/T6).
    # When regime_bias is None the check is False — full back-compat.
    transition_short_bias = (
        regime_class == RegimeClass.TRANSITION and regime_bias == Direction.SHORT
    )
    triggered = (daily_knife and not intraday_recovery) or transition_short_bias
    if daily_knife and not intraday_recovery and not transition_short_bias:
        detail = (
            f"Fast slope={ta.ma_fast_slope:.4f} < 0 AND price={current_price:.4f} "
            f"< mid MA={ta.ma_mid:.4f} — falling knife (no intraday recovery: "
            f"intraday MA={ta.intraday_ma_fast:.4f}, "
            f"intraday slope={ta.intraday_close_slope:.4f})"
        )
    elif daily_knife and not intraday_recovery and transition_short_bias:
        detail = (
            f"Fast slope={ta.ma_fast_slope:.4f} < 0 AND price={current_price:.4f} "
            f"< mid MA={ta.ma_mid:.4f} — falling knife; ALSO regime TRANSITION "
            f"with bias=SHORT"
        )
    elif daily_knife:
        detail = (
            f"Daily downtrend (slope={ta.ma_fast_slope:.4f}, "
            f"price={current_price:.4f} < mid MA={ta.ma_mid:.4f}) RELEASED by "
            f"intraday recovery: price > intraday MA={ta.intraday_ma_fast:.4f} "
            f"AND intraday slope={ta.intraday_close_slope:.4f} > 0"
        )
    elif transition_short_bias:
        detail = (
            f"Regime TRANSITION with bias=SHORT (slope={ta.ma_fast_slope:.4f}) "
            f"— bearish-leaning reversal, no longs"
        )
    else:
        detail = "No downtrend knife catch detected"
    return _make_result(
        "dnt_09_buying_downtrend",
        "Do Not Buy in Downtrend / Catch Falling Knife",
        triggered,
        detail,
        11.1,
    )


def dnt_10_news_no_structure(
    has_pending_event: bool,
    lines: Sequence[AlgoLine],
) -> DNTResult:
    """DNT 10: News / macro event without structural confirmation."""
    qualified = [ln for ln in lines if len(ln.touch_points) >= 2]
    triggered = has_pending_event and len(qualified) < 1
    return _make_result(
        "dnt_10_news_no_structure",
        "News / Macro Event Without Structure",
        triggered,
        (
            "Macro event pending with no confirmed structure lines"
            if triggered
            else (
                "Macro event pending but structure exists"
                if has_pending_event
                else "No pending macro event"
            )
        ),
        14.0,
    )


def dnt_11_emotional_trading(has_pattern_signal: bool) -> DNTResult:
    """DNT 11: Emotional / bias-driven trading.

    Triggered when no pattern signal exists — may indicate impulse trading.
    """
    triggered = not has_pattern_signal
    return _make_result(
        "dnt_11_emotional_trading",
        "Emotional / Bias-Driven Trading",
        triggered,
        (
            "No completed pattern signal — trade may be bias/emotion driven"
            if triggered
            else "Completed pattern signal exists"
        ),
        8.9,
    )


def dnt_12_low_volume(
    current_volume: float,
    volume_baseline: float,
    threshold: float = 0.50,
) -> DNTResult:
    """DNT 12: Low volume / holiday / shortened session.

    Triggered when current session volume is below threshold of baseline.
    """
    if volume_baseline <= 0:
        return _make_result(
            "dnt_12_low_volume",
            "Low Volume / Holiday / Shortened Session",
            False,
            "No volume baseline available",
            5.8,
        )
    ratio = current_volume / volume_baseline
    triggered = ratio < threshold
    return _make_result(
        "dnt_12_low_volume",
        "Low Volume / Holiday / Shortened Session",
        triggered,
        (
            f"Volume ratio={ratio:.2f} < {threshold} — low volume regime"
            if triggered
            else f"Volume ratio={ratio:.2f} >= {threshold} — normal volume"
        ),
        5.8,
    )


def dnt_13_consecutive_losses(
    consecutive_losses: int,
    max_losses: int = 2,
) -> DNTResult:
    """DNT 13: Stop after N consecutive losses."""
    triggered = consecutive_losses >= max_losses
    return _make_result(
        "dnt_13_consecutive_losses",
        "Stop After Consecutive Losses",
        triggered,
        (
            f"Consecutive losses={consecutive_losses} >= {max_losses} — stop trading"
            if triggered
            else f"Consecutive losses={consecutive_losses} < {max_losses}"
        ),
        1.4,
    )


def dnt_16_extended_at_bb(
    current_price: float,
    ta: TAState,
    intended_direction: Direction,
) -> DNTResult:
    """DNT 16: Price extended at Bollinger Band.

    Long: triggered if price >= upper BB (overextended).
    Short: triggered if price <= lower BB without a structural base.
    """
    if intended_direction == Direction.LONG:
        triggered = current_price >= ta.bb_upper
        reason = (
            f"Price {current_price:.4f} >= upper BB {ta.bb_upper:.4f} — overextended, no long"
            if triggered
            else f"Price {current_price:.4f} < upper BB {ta.bb_upper:.4f} — not extended"
        )
    else:
        triggered = current_price <= ta.bb_lower
        reason = (
            f"Price {current_price:.4f} <= lower BB {ta.bb_lower:.4f} — no structural base"
            if triggered
            else f"Price {current_price:.4f} > lower BB {ta.bb_lower:.4f} — not extended"
        )
    return _make_result(
        "dnt_16_extended_at_bb",
        "Price Extended at Bollinger Band",
        triggered,
        reason,
        1.0,
    )


def dnt_17_risk_undefined(
    entry_price: float,
    stop_price: float,
    target_price: float,
    min_rr: float = 3.0,
) -> DNTResult:
    """DNT 17: Risk cannot be defined to a specific price.

    Triggered when there is no stop defined or R:R is below minimum.
    """
    if entry_price == stop_price:
        return _make_result(
            "dnt_17_risk_undefined",
            "Risk Cannot Be Defined to Specific Price",
            True,
            "Stop price equals entry price — risk is undefined",
            0.0,
        )
    risk = abs(entry_price - stop_price)
    reward = abs(target_price - entry_price)
    rr = reward / risk if risk > 0 else 0.0
    triggered = rr < min_rr
    return _make_result(
        "dnt_17_risk_undefined",
        "Risk Cannot Be Defined to Specific Price",
        triggered,
        (
            f"R:R={rr:.2f} < minimum {min_rr:.1f} — skip or size down"
            if triggered
            else f"R:R={rr:.2f} >= {min_rr:.1f} — acceptable risk"
        ),
        0.0,
    )


# ---------------------------------------------------------------------------
# Universal aggregator
# ---------------------------------------------------------------------------


def run_universal_dnt_filters(
    candles: Sequence[Candle],
    lines: Sequence[AlgoLine],
    regime: RegimeClassification,
    ta_state: TAState,
    trade_count: int,
    config: AssetConfig | None = None,
    *,
    current_price: float | None = None,
    trigger_level: float | None = None,
    intended_direction: Direction = Direction.LONG,
    wedge_upper: float | None = None,
    wedge_lower: float | None = None,
    has_pending_event: bool = False,
    has_pattern_signal: bool = True,
    current_volume: float = 0.0,
    volume_baseline: float = 0.0,
    consecutive_losses: int = 0,
    entry_price: float | None = None,
    stop_price: float | None = None,
    target_price: float | None = None,
) -> list[DNTResult]:
    """Run all universal DNT filters and return results.

    Runs 13+ filters that are asset-agnostic. SPY-specific filters
    (opening trap, VWAP EOD, IV/theta, mobile) are not included.

    Args:
        candles: Price bars (most-recent last).
        lines: Detected algorithmic lines.
        regime: Current regime classification.
        ta_state: Current TA state.
        trade_count: Number of trades taken today.
        config: Asset configuration. Defaults to SPY.
        current_price: Latest price (defaults to last candle close).
        trigger_level: Breakout trigger level for filters 03, 07.
        intended_direction: LONG or SHORT — for filters 06, 09, 16.
        wedge_upper / wedge_lower: Wedge boundaries for filter 04.
        has_pending_event: True if macro event pending.
        has_pattern_signal: True if a completed pattern was detected.
        current_volume / volume_baseline: For filter 12.
        consecutive_losses: For filter 13.
        entry_price / stop_price / target_price: For filter 17.

    Returns:
        List of DNTResult (one per filter evaluated).
    """
    cfg = config if config is not None else get_config("SPY")

    if current_price is None:
        current_price = candles[-1].close if candles else 0.0

    results: list[DNTResult] = []

    results.append(dnt_01_no_structure(lines))
    results.append(dnt_02_choppy(candles, cfg.choppy_range_threshold))

    if trigger_level is not None:
        results.append(dnt_03_no_breakout_confirmation(candles, trigger_level, intended_direction))

    if wedge_upper is not None and wedge_lower is not None:
        results.append(dnt_04_inside_wedge(candles, wedge_upper, wedge_lower))

    results.append(dnt_05_trapped_between_mas(current_price, ta_state))
    results.append(
        dnt_06_no_short_uptrend(
            ta_state, intended_direction, regime.regime_class, regime_bias=regime.bias
        )
    )

    if trigger_level is not None:
        results.append(
            dnt_07_chasing_missed_entry(
                current_price, trigger_level, intended_direction, cfg.chase_threshold_pct
            )
        )

    results.append(dnt_08_overtrading(trade_count, cfg.max_trades_per_day))
    results.append(
        dnt_09_buying_downtrend(
            ta_state,
            current_price,
            intended_direction,
            regime_class=regime.regime_class,
            regime_bias=regime.bias,
        )
    )
    results.append(dnt_10_news_no_structure(has_pending_event, lines))
    results.append(dnt_11_emotional_trading(has_pattern_signal))
    results.append(dnt_12_low_volume(current_volume, volume_baseline))
    results.append(dnt_13_consecutive_losses(consecutive_losses, cfg.max_consecutive_losses))
    results.append(dnt_16_extended_at_bb(current_price, ta_state, intended_direction))

    if entry_price is not None and stop_price is not None and target_price is not None:
        results.append(dnt_17_risk_undefined(entry_price, stop_price, target_price))

    return results
