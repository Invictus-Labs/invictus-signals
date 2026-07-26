"""Technical analysis calculations for invictus-signals.

Provides SMA, Bollinger Bands, VWAP, slope, RSI, MACD histogram,
ADX, and ATR calculations. All functions are pure and deterministic.
Config-driven MA periods support all asset types.
"""
from __future__ import annotations

import math
from typing import Sequence

from invictus_signals.config import AssetConfig, get_config
from invictus_signals.models import Candle, TAState


# ---------------------------------------------------------------------------
# Primitive calculations
# ---------------------------------------------------------------------------


def calculate_sma(prices: Sequence[float], period: int) -> float:
    """Simple moving average of the last *period* values.

    Args:
        prices: Price series (at least *period* elements long).
        period: Look-back window.

    Returns:
        The SMA value.

    Raises:
        ValueError: If prices is shorter than period or period < 1.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    if len(prices) < period:
        raise ValueError(f"Need at least {period} prices, got {len(prices)}")
    window = prices[-period:]
    return sum(window) / period


def calculate_bb(
    prices: Sequence[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> dict[str, float]:
    """Bollinger Bands (upper, middle, lower, width).

    Args:
        prices: Price series (at least *period* elements long).
        period: SMA period for the middle band (default 20).
        std_dev: Standard deviation multiplier (default 2.0).

    Returns:
        Dict with keys: ``upper``, ``middle``, ``lower``, ``width``.
        ``width`` is (upper - lower) / middle — the normalized bandwidth.

    Raises:
        ValueError: If insufficient data or period < 2.
    """
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")
    if len(prices) < period:
        raise ValueError(f"Need at least {period} prices, got {len(prices)}")
    window = list(prices[-period:])
    middle = sum(window) / period
    variance = sum((p - middle) ** 2 for p in window) / period
    sigma = math.sqrt(variance)
    band = std_dev * sigma
    upper = middle + band
    lower = middle - band
    width = (upper - lower) / middle if middle != 0.0 else 0.0
    return {"upper": upper, "middle": middle, "lower": lower, "width": width}


def bbwp(
    widths: Sequence[float],
    lookback: int,
    min_samples: int = 2,
) -> float | None:
    """Percentile rank (0-100) of the FINAL element of *widths* within the
    trailing *lookback* window (Bollinger Band Width Percentile).

    Stdlib only — no numpy/scipy. Hand-rolled rank: take the trailing window,
    then count how many of the *other* elements the final element beats.

    Rank convention (load-bearing — read before changing):
        **Strictly-less-than.** For each other element ``w`` in the window,
        it counts toward the numerator iff ``w < target`` (ties do NOT count).
        percentile = 100 * count_strictly_less / (window_size - 1).
        Consequence: a fresh window all-time-HIGH (target is the unique max)
        reads as exactly 100.0; a fresh all-time-LOW reads as exactly 0.0.
        A less-or-equal convention would also send a unique max to 100, but
        would inflate the rank of any value merely *tied* with lesser peers —
        strictly-less-than is the more conservative, more common convention
        (mirrors the community BBWP scripts this metric is named after) and
        is what this function implements.

    Degenerate case — every value in the window is identical:
        Returns **50.0** (neutral), not 100.0, 0.0, or None. Rationale: a
        constant window has nothing to rank against, so neither "extremely
        compressed" (0) nor "extremely expanded" (100) is true — reporting an
        extreme would tell a downstream bucket exactly the wrong thing. 50.0
        (the NORMAL bucket) is also distinct from ``None``, which this
        function reserves for "cannot compute at all" (e.g. insufficient
        history) — a flat-but-present window is a different failure mode
        than a missing one and must not collapse to the same sentinel.

    Sad paths (all return ``None`` — never a guessed number):
        - ``len(widths) < min_samples`` — not enough history at all.
        - ``lookback <= 1`` — a window of 0 or 1 elements has nothing to rank
          the final element against (the denominator would be <= 0).
        - The final element itself is NaN — an undefined target cannot be
          ranked.
        - After dropping non-finite (NaN/inf) elements from the *other*
          window members, zero valid comparison points remain (every other
          window member was itself NaN/inf) — same reasoning as the
          lookback<=1 case, just discovered after filtering.

    Other behavior:
        - **Fewer elements than lookback but >= min_samples**: ranks within
          whatever is actually available — ``effective_lookback =
          min(lookback, len(widths))`` — the same degrade-gracefully pattern
          `compute_ta_state` already uses for its MA/BB periods. This is not
          a guess; it is ranking against a smaller, but still real, window.
        - **NaN elsewhere in the window** (not the target): excluded from
          both the numerator and the denominator rather than counted as
          "not less than" — comparing against NaN is well-defined in Python
          (always False) but silently deflates the percentile if left in the
          denominator, so it is filtered out instead.
        - **Negative widths**: not special-cased. A Bollinger bandwidth is
          structurally non-negative in practice, but this function only
          ranks floats — it does not validate width semantics — so a
          negative value (or any float) compares and ranks normally.

    Args:
        widths: Historical bandwidth series (e.g. `TAState.bb_width` values
            over time), most-recent last. The last element is the one being
            ranked.
        lookback: Trailing window size to rank within. Caller-supplied —
            this library hardcodes no lookback (per-asset calibration is a
            bot-level decision; see the PRD's D-2).
        min_samples: Minimum total history required before a rank is
            attempted (the floor is 2 — the mathematical minimum for a rank
            to exist at all: the target plus one point to compare against).

    Returns:
        Percentile rank 0.0-100.0, or None per the sad paths above.
    """
    if len(widths) < min_samples:
        return None
    if lookback <= 1:
        return None

    effective_lookback = min(lookback, len(widths))
    window = list(widths[-effective_lookback:])
    target = window[-1]

    if math.isnan(target):
        return None

    comparable = [w for w in window[:-1] if math.isfinite(w)]
    if len(comparable) < 1:
        return None

    if all(w == target for w in comparable):
        return 50.0

    count_less = sum(1 for w in comparable if w < target)
    return 100.0 * count_less / len(comparable)


def _rolling_bb_widths(
    closes: Sequence[float],
    period: int,
    std_dev: float,
) -> list[float]:
    """Bollinger bandwidth at every trailing position along *closes* where a
    full *period*-length window exists, most-recent last.

    Private helper feeding `bbwp()`: a percentile rank needs a series of
    *actually realized* historical widths, not one snapshot repeated — so
    this recomputes `calculate_bb`'s width at each position rather than
    inventing a second normalization. The last element always equals a
    direct `calculate_bb(closes, period, std_dev)["width"]` call on the same
    *closes* — same window, same guard (a zero/near-zero middle yields 0.0,
    never a ZeroDivisionError, per `calculate_bb`).

    Returns an empty list if *period* < 2 or there isn't a full window yet
    (never raises — callers treat an empty result as "nothing to rank").
    """
    if period < 2 or len(closes) < period:
        return []
    return [
        calculate_bb(closes[: i + 1], period=period, std_dev=std_dev)["width"]
        for i in range(period - 1, len(closes))
    ]


def calculate_vwap(candles: Sequence[Candle]) -> float:
    """Volume-weighted average price over a sequence of candles.

    Uses the typical price (H+L+C)/3 per bar.

    Args:
        candles: Non-empty sequence of Candle objects.

    Returns:
        VWAP as a float.

    Raises:
        ValueError: If candles is empty or total volume is zero.
    """
    if not candles:
        raise ValueError("candles must not be empty")
    cum_tpv = 0.0
    cum_vol = 0.0
    for c in candles:
        typical = (c.high + c.low + c.close) / 3.0
        cum_tpv += typical * c.volume
        cum_vol += c.volume
    if cum_vol == 0.0:
        raise ValueError("Total volume is zero — cannot compute VWAP")
    return cum_tpv / cum_vol


def calculate_slope(values: Sequence[float], period: int = 5) -> float:
    """Slope of a linear regression fitted to the last *period* values.

    Uses ordinary least-squares. The slope is in units of
    value-per-bar (i.e., rise per 1 index step).

    Args:
        values: Value series (at least *period* elements long).
        period: Number of trailing values to fit (default 5).

    Returns:
        OLS slope coefficient.

    Raises:
        ValueError: If insufficient data or period < 2.
    """
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")
    if len(values) < period:
        raise ValueError(f"Need at least {period} values, got {len(values)}")
    window = list(values[-period:])
    n = period
    xs = list(range(n))
    x_mean = (n - 1) / 2.0
    y_mean = sum(window) / n
    numerator = sum((xs[i] - x_mean) * (window[i] - y_mean) for i in range(n))
    denominator = sum((xs[i] - x_mean) ** 2 for i in range(n))
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def calculate_rsi(prices: Sequence[float], period: int = 14) -> float:
    """Relative Strength Index (RSI) using Wilder's smoothing.

    Args:
        prices: Price series (at least period + 1 elements).
        period: RSI period (default 14).

    Returns:
        RSI value 0-100. Returns 50.0 if insufficient data.
    """
    if len(prices) < period + 1:
        return 50.0
    closes = list(prices[-(period + 1):])
    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_macd_histogram(
    prices: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> float:
    """MACD histogram (MACD line minus signal line).

    Uses exponential moving averages.

    Args:
        prices: Price series (at least slow + signal elements).
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal EMA period (default 9).

    Returns:
        MACD histogram value. Returns 0.0 if insufficient data.
    """
    needed = slow + signal
    if len(prices) < needed:
        return 0.0

    def _ema(data: list[float], n: int) -> list[float]:
        k = 2.0 / (n + 1)
        result = [data[0]]
        for p in data[1:]:
            result.append(p * k + result[-1] * (1.0 - k))
        return result

    closes = list(prices)
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(closes))]
    if len(macd_line) < signal:
        return 0.0
    signal_line = _ema(macd_line, signal)
    return macd_line[-1] - signal_line[-1]


def calculate_atr(candles: Sequence[Candle], period: int = 14) -> float:
    """Average True Range over *period* candles.

    Args:
        candles: Candle series (at least period + 1 elements).
        period: ATR period (default 14).

    Returns:
        ATR value. Returns 0.0 if insufficient data.
    """
    if len(candles) < 2:
        return 0.0
    trs = []
    bars = list(candles[-(period + 1):])
    for i in range(1, len(bars)):
        c = bars[i]
        prev_close = bars[i - 1].close
        tr = max(
            c.high - c.low,
            abs(c.high - prev_close),
            abs(c.low - prev_close),
        )
        trs.append(tr)
    if not trs:
        return 0.0
    return sum(trs) / len(trs)


def calculate_adx(candles: Sequence[Candle], period: int = 14) -> float:
    """Average Directional Index (ADX) — measures trend strength.

    Simplified implementation using True Range and directional movement.

    Args:
        candles: Candle series (at least 2 * period elements recommended).
        period: ADX period (default 14).

    Returns:
        ADX value 0-100. Returns 0.0 if insufficient data.
    """
    needed = period * 2
    if len(candles) < needed:
        return 0.0

    bars = list(candles[-needed:])
    plus_dms = []
    minus_dms = []
    trs = []

    for i in range(1, len(bars)):
        high_diff = bars[i].high - bars[i - 1].high
        low_diff = bars[i - 1].low - bars[i].low
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - bars[i - 1].close),
            abs(bars[i].low - bars[i - 1].close),
        )
        trs.append(tr)
        plus_dms.append(high_diff if high_diff > low_diff and high_diff > 0 else 0.0)
        minus_dms.append(low_diff if low_diff > high_diff and low_diff > 0 else 0.0)

    def _smooth(values: list[float], n: int) -> list[float]:
        """Wilder smoothing."""
        if len(values) < n:
            return []
        result = [sum(values[:n])]
        for v in values[n:]:
            result.append(result[-1] - result[-1] / n + v)
        return result

    sm_tr = _smooth(trs, period)
    sm_plus = _smooth(plus_dms, period)
    sm_minus = _smooth(minus_dms, period)

    if not sm_tr or sm_tr[-1] == 0.0:
        return 0.0

    plus_di = 100.0 * sm_plus[-1] / sm_tr[-1]
    minus_di = 100.0 * sm_minus[-1] / sm_tr[-1]
    di_sum = plus_di + minus_di
    if di_sum == 0.0:
        return 0.0
    dx = 100.0 * abs(plus_di - minus_di) / di_sum

    # Return DX as a proxy for ADX (single-period approximation)
    return dx


# ---------------------------------------------------------------------------
# Full TAState computation
# ---------------------------------------------------------------------------


def compute_ta_state(
    candles: Sequence[Candle],
    daily_candles: Sequence[Candle],
    config: AssetConfig | None = None,
    vol_lookback: int | None = None,
) -> TAState:
    """Compute the full TAState from intraday + daily candle history.

    The *daily_candles* provide multi-period moving averages and Bollinger
    Bands. The *candles* (intraday) are used for VWAP and volume MA.
    Periods come from the AssetConfig (defaults to SPY).

    Args:
        candles: Intraday bars for the current session (most-recent last).
        daily_candles: Daily OHLCV bars (most-recent last).
        config: Asset configuration. Defaults to SPY preset.
        vol_lookback: Trailing window for the BBWP percentile rank
            (`bbwp()`), applied to BOTH `bb_width_pct` (daily) and
            `intraday_bb_width_pct` (intraday) — mirroring how
            `intraday_bb_upper`/`intraday_bb_lower` reuse the daily
            `bb_period`/`bb_std_dev` rather than inventing a second
            constant. **No default is hardcoded here** — per-asset
            calibration is a bot-level decision (PRD D-2); when omitted
            (`None`, the default), both `_pct` fields stay `None` and this
            function's behavior for every existing field is unchanged from
            before this parameter existed (additive-only, AC-6).

    Returns:
        Populated TAState.

    Raises:
        ValueError: If either series is empty.
    """
    if not candles:
        raise ValueError("candles must not be empty")
    if not daily_candles:
        raise ValueError("daily_candles must not be empty")

    cfg = config if config is not None else get_config("SPY")

    daily_closes = [c.close for c in daily_candles]
    intraday_volumes = [c.volume for c in candles]
    n_daily = len(daily_closes)

    # --- Daily MAs ---
    period_fast = min(cfg.ma_fast_period, n_daily)
    period_mid = min(cfg.ma_mid_period, n_daily)
    period_slow = min(cfg.ma_slow_period, n_daily)

    ma_fast = calculate_sma(daily_closes, period_fast)
    ma_mid = calculate_sma(daily_closes, period_mid)
    ma_slow = calculate_sma(daily_closes, period_slow)

    # --- MA slopes ---
    slope_period = min(5, n_daily)
    if slope_period >= 2:
        ma_fast_slope = calculate_slope(daily_closes, slope_period)
        ma_mid_slope = calculate_slope(daily_closes, slope_period)
    else:
        ma_fast_slope = 0.0
        ma_mid_slope = 0.0

    # --- Bollinger Bands ---
    bb_period = min(cfg.bb_period, n_daily)
    if bb_period >= 2:
        bb = calculate_bb(daily_closes, period=bb_period, std_dev=cfg.bb_std_dev)
    else:
        last = daily_closes[-1]
        bb = {"upper": last, "middle": last, "lower": last, "width": 0.0}

    bb_slope_period = min(5, n_daily)
    if bb_slope_period >= 2:
        bb_upper_slope = calculate_slope(daily_closes, bb_slope_period)
    else:
        bb_upper_slope = 0.0

    # --- Intraday structure (same fast period as the daily MA, applied to the
    # intraday bars — e.g. ma_fast_period=12 on 1h candles = 12-hour SMA; slope
    # is the OLS slope of the last 5 intraday closes).
    # Gives daily-scale filters (dnt_09) a current-session lens: a multi-day
    # dump keeps the daily 5-day slope negative for days and price below the
    # 26-day SMA for weeks, long after the intraday structure has reversed
    # (observed 2026-06-06/07: 530 dnt_09 blocks across BTC/ETH/SOL/BNB
    # through an intraday V-recovery).
    intraday_closes = [c.close for c in candles]
    n_intraday = len(intraday_closes)
    intraday_ma_fast = calculate_sma(
        intraday_closes, min(cfg.ma_fast_period, n_intraday)
    )
    # Intraday mid MA — same mid period as the daily MA, on the intraday bars.
    # dnt_05 ("trapped between MAs") needs the fast/mid band on the entry
    # timeframe; the daily band stays fixed for days after a multi-day move.
    intraday_ma_mid = calculate_sma(
        intraday_closes, min(cfg.ma_mid_period, n_intraday)
    )
    # Intraday Bollinger Bands — same period/std as the daily BB, on the
    # intraday bars. dnt_16 ("extended at BB") tests price against the
    # entry-timeframe band, not the stale daily one. Needs >=2 bars to compute
    # a band; otherwise 0.0 sentinel → dnt_16 falls back to the daily BB.
    intraday_bb_period = min(cfg.bb_period, n_intraday)
    if intraday_bb_period >= 2:
        intraday_bb = calculate_bb(
            intraday_closes, period=intraday_bb_period, std_dev=cfg.bb_std_dev
        )
        intraday_bb_upper = intraday_bb["upper"]
        intraday_bb_lower = intraday_bb["lower"]
        intraday_bb_width = intraday_bb["width"]
    else:
        intraday_bb_upper = 0.0
        intraday_bb_lower = 0.0
        intraday_bb_width = 0.0

    # --- Bandwidth percentiles (BBWP, additive — four-layer-order PRD Phase 1).
    # Only attempted when the caller supplies a lookback; otherwise both stay
    # None (see vol_lookback's docstring). Ranks the FINAL element of a
    # rolling widths series built from calculate_bb at every trailing
    # position, so the target being ranked is always identical to bb["width"]
    # / intraday_bb["width"] above — never a second, divergent computation.
    if vol_lookback is not None and bb_period >= 2:
        daily_widths = _rolling_bb_widths(daily_closes, bb_period, cfg.bb_std_dev)
        bb_width_pct = bbwp(daily_widths, vol_lookback)
    else:
        bb_width_pct = None

    if vol_lookback is not None and intraday_bb_period >= 2:
        intraday_widths = _rolling_bb_widths(
            intraday_closes, intraday_bb_period, cfg.bb_std_dev
        )
        intraday_bb_width_pct = bbwp(intraday_widths, vol_lookback)
    else:
        intraday_bb_width_pct = None

    intraday_slope_period = min(5, n_intraday)
    if intraday_slope_period >= 2:
        intraday_close_slope = calculate_slope(intraday_closes, intraday_slope_period)
    else:
        intraday_close_slope = 0.0

    # Intraday trend strength: ADX on the *intraday* bars (the entry timeframe).
    # This is the discriminator the trend-strength gate keys off — winners enter
    # on a strongly-trending 1H, losers on a choppy 1H. Distinct from the daily
    # `adx` below, which is computed from daily_candles.
    intraday_adx = calculate_adx(list(candles))

    # --- Volume MA (intraday) ---
    vol_period = min(cfg.volume_ma_period, len(intraday_volumes))
    volume_ma = calculate_sma(intraday_volumes, vol_period)

    # --- VWAP (intraday session) ---
    vwap = calculate_vwap(candles)

    # --- Extended indicators ---
    rsi = calculate_rsi(daily_closes)
    macd_histogram = calculate_macd_histogram(daily_closes)
    atr_val = calculate_atr(list(daily_candles))
    atr_pct = (atr_val / daily_closes[-1]) if daily_closes[-1] != 0.0 else 0.0
    adx = calculate_adx(list(daily_candles))

    return TAState(
        ma_fast=ma_fast,
        ma_mid=ma_mid,
        ma_slow=ma_slow,
        ma_fast_slope=ma_fast_slope,
        ma_mid_slope=ma_mid_slope,
        bb_upper=bb["upper"],
        bb_lower=bb["lower"],
        bb_middle=bb["middle"],
        bb_width=bb["width"],
        bb_upper_slope=bb_upper_slope,
        volume_ma=volume_ma,
        vwap=vwap,
        rsi=rsi,
        macd_histogram=macd_histogram,
        atr=atr_val,
        atr_pct=atr_pct,
        adx=adx,
        intraday_ma_fast=intraday_ma_fast,
        intraday_close_slope=intraday_close_slope,
        intraday_adx=intraday_adx,
        intraday_ma_mid=intraday_ma_mid,
        intraday_bb_upper=intraday_bb_upper,
        intraday_bb_lower=intraday_bb_lower,
        bb_width_pct=bb_width_pct,
        intraday_bb_width=intraday_bb_width,
        intraday_bb_width_pct=intraday_bb_width_pct,
    )
