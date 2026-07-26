"""Core data models for invictus-signals.

All trading concepts are represented as dataclasses with type hints.
Field names use generic terminology (ma_fast, ma_mid, ma_slow) so the
models work across all asset types — not just SPY.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RegimeClass(Enum):
    """Four macro market regime classes."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    CHOPPY = "choppy"
    TRANSITION = "transition"


class RegimeId(Enum):
    """33-regime identifiers (B1-B8, BR1-BR8, C1-C8, T1-T9)."""
    # Bullish (B1-B8)
    B1_TRENDING = "b1_trending"
    B2_CONTINUATION = "b2_continuation"
    B3_CHANNEL = "b3_channel"
    B4_MOMENTUM = "b4_momentum"
    B5_ACCUMULATION = "b5_accumulation"
    B6_CUP_HANDLE = "b6_cup_handle"
    B7_HL_DEFENSE = "b7_hl_defense"
    B8_REVERSAL_OVERSOLD = "b8_reversal_oversold"
    # Bearish (BR1-BR8)
    BR1_AGGRESSIVE = "br1_aggressive"
    BR2_CONTINUATION = "br2_continuation"
    BR3_HIGH_MOMENTUM = "br3_high_momentum"
    BR4_MACRO = "br4_macro"
    BR5_SLOPE_CONFIRM = "br5_slope_confirm"
    BR6_TECHNICAL = "br6_technical"
    BR7_FEAR_DRIVEN = "br7_fear_driven"
    BR8_INVERSE_CUP = "br8_inverse_cup"
    # Choppy (C1-C8)
    C1_COMPRESSION = "c1_compression"
    C2_RANGE = "c2_range"
    C3_FLAG = "c3_flag"
    C4_VOLATILITY = "c4_volatility"
    C5_INSIDE_BAR = "c5_inside_bar"
    C6_SQUEEZE = "c6_squeeze"
    C7_OSCILLATION = "c7_oscillation"
    C8_DRIFT = "c8_drift"
    # Transition (T1-T9)
    T1_MEAN_REVERSION = "t1_mean_reversion"
    T2_MA_CROSSOVER = "t2_ma_crossover"
    T3_BULL_REVERSAL = "t3_bull_reversal"
    T4_PLATEAU_RECLAIM = "t4_plateau_reclaim"
    T5_BEAR_REVERSAL = "t5_bear_reversal"
    T6_HL_BREACH = "t6_hl_breach"
    T7_CHANNEL_BREAK = "t7_channel_break"
    T8_POST_BOUNCE = "t8_post_bounce"
    T9_EXHAUSTION = "t9_exhaustion"


class Direction(Enum):
    LONG = "long"
    SHORT = "short"


class LineColor(Enum):
    """7-color algorithm line hierarchy. Priority order = enum order."""
    MAGENTA = "magenta"   # P1 — Macro algorithmic control
    ORANGE = "orange"     # P2 — Intraday trend + key levels
    GREEN = "green"       # P3 — Precision continuation
    TEAL = "teal"         # P4 — Breakout confirmation
    YELLOW = "yellow"     # P5 — Macro structure / horizontals
    PINK = "pink"         # P6 — Cup rim / trigger line
    BLUE = "blue"         # P7 — Exhaustion / tapering


class LineType(Enum):
    ASCENDING_SUPPORT = "ascending_support"
    DESCENDING_RESISTANCE = "descending_resistance"
    HORIZONTAL = "horizontal"
    CHANNEL_UPPER = "channel_upper"
    CHANNEL_LOWER = "channel_lower"
    TRENDLINE = "trendline"
    WEDGE_UPPER = "wedge_upper"
    WEDGE_LOWER = "wedge_lower"


class ValidationStatus(Enum):
    UNVALIDATED = "unvalidated"
    CORRECTED = "corrected"
    ADJUSTED = "adjusted"
    REFRAMED = "reframed"
    REMOVED = "removed"
    VALIDATED = "validated"


class ConvictionLevel(Enum):
    HIGH = "high"         # Full size — all lines aligned
    MODERATE = "moderate" # Standard size
    LOW = "low"           # Reduced size or skip


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------


@dataclass
class Candle:
    """Single OHLCV bar."""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TAState:
    """Technical analysis state at a point in time.

    Generic field names (ma_fast/ma_mid/ma_slow) work across all assets.
    The periods behind these names are configured via AssetConfig.
    """
    ma_fast: float
    ma_mid: float
    ma_slow: float
    ma_fast_slope: float
    ma_mid_slope: float
    bb_upper: float
    bb_lower: float
    bb_middle: float
    bb_width: float
    bb_upper_slope: float
    volume_ma: float
    vwap: float
    # Extended indicators (default to neutral values)
    rsi: float = 50.0
    macd_histogram: float = 0.0
    adx: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    # Intraday structure (from the intraday candles arg of compute_ta_state).
    # Defaults are sentinel "no intraday data": consumers that gate on these
    # (e.g. dnt_09's recovery release, dnt_05's fast/mid band) must treat 0.0 as
    # absent and fall back to daily-only behavior, so TAStates built without them
    # are unchanged. ma_fast/ma_mid are co-populated and used together by dnt_05.
    intraday_ma_fast: float = 0.0
    intraday_ma_mid: float = 0.0
    intraday_close_slope: float = 0.0
    # Intraday trend strength (ADX on the intraday bars). The entry-timeframe
    # trend-strength gate keys off this: momentum/breakout patterns only have
    # edge when the 1H is genuinely trending; in 1H chop they get faded both
    # ways. Daily ADX is the WRONG lens (a trending daily can sit on a choppy
    # 1H — empirically inverted vs outcomes). 0.0 = no intraday data (absent).
    intraday_adx: float = 0.0
    # Intraday Bollinger bands for the same-timeframe band gate (dnt_16). The
    # daily BB sits far from intraday price for days after a multi-day move, so
    # dnt_16 ("extended at BB") mis-fires on the 15m/1h entry timeframe (same
    # daily-scale class as dnt_05/HYPE 2026-06-05). Presence is keyed off the
    # upper band (always > 0 for positive prices); 0.0 = absent → daily fallback.
    intraday_bb_upper: float = 0.0
    intraday_bb_lower: float = 0.0
    # Bandwidth percentiles (BBWP) — additive, Phase 1 of the four-layer-order
    # PRD (docs/prd/four-layer-order/four-layer-order.md, AC-6). Two separate
    # scales, mirroring why intraday_bb_upper/lower exist alongside the daily
    # bb_upper/lower (PR #7, dnt_16 precedent): a regime-scale read and an
    # entry-timeframe read answer different questions and must not collapse
    # into one field.
    #   bb_width_pct          — percentile of the DAILY bandwidth (regime-scale,
    #                            "is the daily leg coiled or spent").
    #   intraday_bb_width      — normalized INTRADAY bandwidth, same (u-l)/mid
    #                            form as bb_width, just computed on the
    #                            intraday closes. No lookback needed — it is
    #                            the current snapshot, not a rank.
    #   intraday_bb_width_pct  — percentile of the INTRADAY bandwidth
    #                            (entry-scale, what dnt_16-style consumers on
    #                            the 15m/1h timeframe should key off).
    # None on the two `_pct` fields means "not computed" — either the caller
    # didn't supply a lookback, or `bbwp()` returned None (see its docstring
    # for the sad paths: insufficient history, lookback<=1, NaN target).
    # Never interpolated or guessed. 0.0 on `intraday_bb_width` is the same
    # "absent" sentinel already used by intraday_bb_upper/lower.
    bb_width_pct: float | None = None
    intraday_bb_width: float = 0.0
    intraday_bb_width_pct: float | None = None


@dataclass
class RegimeClassification:
    """Result of classifying the current market regime."""
    regime_id: RegimeId
    regime_class: RegimeClass
    bias: Direction | None         # None for choppy
    size_multiplier: float         # 0.0, 0.25, 0.50, 1.0
    conditions_met: list[str]      # Which measurable conditions matched
    confidence: float              # 0-1


@dataclass
class AlgoLine:
    """A detected algorithm line (one of 7 colors)."""
    color: LineColor
    line_type: LineType
    touch_points: list[tuple[float, float]]  # (timestamp, price)
    slope: float
    current_level: float           # Interpolated level at current time
    session_frequency: float       # % of sessions this color appears


@dataclass
class PatternMatch:
    """A detected entry pattern."""
    pattern_id: str
    name: str
    direction: Direction
    trigger_price: float
    stop_price: float
    target_prices: list[float]
    invalidation: str
    confidence: float
    lines_involved: list[LineColor]
    frequency_pct: float
    video_refs: list[str]
    validation_status: ValidationStatus


@dataclass
class DNTResult:
    """Result of a single Do-Not-Trade filter check."""
    filter_id: str
    name: str
    triggered: bool
    reason: str
    frequency_pct: float
