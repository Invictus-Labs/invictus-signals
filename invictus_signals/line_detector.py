"""7-color algorithm line detection for invictus-signals.

Detects the 7-color line hierarchy (P1 Magenta through P7 Blue) from
multi-timeframe candle data. Config drives tolerance and round-number
snap so the detector works on any asset (SPY $5 snaps vs BTC $1000 snaps).

Detection approach per color:
  P1 Magenta  — Multi-day trendlines from daily candle highs/lows
  P2 Orange   — Intraday channel from swing points
  P3 Green    — Post-breakout continuation channel (recent bars)
  P4 Teal     — Short-term counter-trend pullback lines
  P5 Yellow   — Horizontal S/R: prior-day pivots + round numbers
  P6 Pink     — Cup rim / session horizontal trigger level
  P7 Blue     — Narrowing-range exhaustion / tapering lines
"""
from __future__ import annotations

from invictus_signals.config import AssetConfig, get_config
from invictus_signals.models import AlgoLine, Candle, LineColor, LineType


# ---------------------------------------------------------------------------
# Linear regression helpers (stdlib only — no numpy)
# ---------------------------------------------------------------------------


def _linear_regression(
    xs: list[float],
    ys: list[float],
) -> tuple[float, float, float]:
    """Ordinary least-squares linear regression.

    Returns (slope, intercept, r_squared).
    r_squared is 0.0 when there is no variance in y.
    """
    n = len(xs)
    if n != len(ys):
        raise ValueError("xs and ys must have the same length")
    if n < 2:
        raise ValueError("Need at least 2 points for regression")

    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(xs[i] * ys[i] for i in range(n))
    sum_x2 = sum(x * x for x in xs)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0.0:
        return 0.0, sum_y / n, 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    if ss_tot == 0.0:
        return slope, intercept, 1.0

    ss_res = sum((ys[i] - (slope * xs[i] + intercept)) ** 2 for i in range(n))
    r_squared = max(0.0, 1.0 - ss_res / ss_tot)
    return slope, intercept, r_squared


# ---------------------------------------------------------------------------
# Swing-point detection
# ---------------------------------------------------------------------------


def find_swing_points(
    candles: list[Candle],
    lookback: int = 5,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Find swing highs and swing lows using a pivot lookback.

    Args:
        candles:  Candle list (oldest first).
        lookback: Bars on each side of the candidate pivot.

    Returns:
        (swing_highs, swing_lows) — each is a list of (bar_index, price).
    """
    n = len(candles)
    if n < 2 * lookback + 1:
        return [], []

    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []

    for i in range(lookback, n - lookback):
        window_start = i - lookback
        window_end = i + lookback + 1

        candidate_high = candles[i].high
        window_highs = [candles[j].high for j in range(window_start, window_end) if j != i]
        if all(candidate_high >= h for h in window_highs):
            swing_highs.append((i, candidate_high))

        candidate_low = candles[i].low
        window_lows = [candles[j].low for j in range(window_start, window_end) if j != i]
        if all(candidate_low <= lo for lo in window_lows):
            swing_lows.append((i, candidate_low))

    return swing_highs, swing_lows


# ---------------------------------------------------------------------------
# Trendline fitting
# ---------------------------------------------------------------------------


def fit_trendline(
    points: list[tuple[int, float]],
) -> tuple[float, float, float]:
    """Fit a linear regression through (index, price) pivot points.

    Returns (slope, intercept, r_squared).
    """
    if len(points) < 2:
        if len(points) == 1:
            return 0.0, points[0][1], 0.0
        return 0.0, 0.0, 0.0

    xs = [float(p[0]) for p in points]
    ys = [p[1] for p in points]
    return _linear_regression(xs, ys)


# ---------------------------------------------------------------------------
# Touch-point counting
# ---------------------------------------------------------------------------


def calculate_touch_points(
    candles: list[Candle],
    slope: float,
    intercept: float,
    tolerance_pct: float = 0.001,
) -> list[tuple[float, float]]:
    """Find candles that touch a trendline within tolerance.

    Args:
        candles:       Candle list (oldest first).
        slope:         Trendline slope (price units per bar).
        intercept:     Trendline intercept.
        tolerance_pct: Fractional tolerance (0.001 = 0.1%).

    Returns:
        List of (timestamp, touch_price) tuples.
    """
    touches: list[tuple[float, float]] = []
    for i, c in enumerate(candles):
        line_price = slope * i + intercept
        if line_price <= 0.0:
            continue
        tol = line_price * tolerance_pct
        for price in (c.open, c.high, c.low, c.close):
            if abs(price - line_price) <= tol:
                touches.append((c.timestamp, price))
                break
    return touches


# ---------------------------------------------------------------------------
# Horizontal level detection
# ---------------------------------------------------------------------------


def find_horizontal_levels(
    candles: list[Candle],
    tolerance_pct: float = 0.001,
    min_touches: int = 2,
) -> list[float]:
    """Find price levels where price has reversed at least *min_touches* times.

    Args:
        candles:       Candle list.
        tolerance_pct: Cluster merge radius as fraction of price.
        min_touches:   Minimum pivot count per cluster.

    Returns:
        List of horizontal price levels (sorted ascending).
    """
    highs, lows = find_swing_points(candles, lookback=5)
    all_pivots = [p for _, p in highs] + [p for _, p in lows]

    if not all_pivots:
        return []

    all_pivots.sort()
    clusters: list[list[float]] = []

    for price in all_pivots:
        placed = False
        for cluster in clusters:
            centroid = sum(cluster) / len(cluster)
            if centroid > 0 and abs(price - centroid) / centroid <= tolerance_pct:
                cluster.append(price)
                placed = True
                break
        if not placed:
            clusters.append([price])

    return [
        sum(c) / len(c)
        for c in clusters
        if len(c) >= min_touches
    ]


# ---------------------------------------------------------------------------
# Channel detection helper
# ---------------------------------------------------------------------------


def detect_channel(
    candles: list[Candle],
    min_touches: int = 2,
) -> tuple[AlgoLine, AlgoLine] | None:
    """Detect a price channel from swing points.

    Returns (upper_line, lower_line) or None if not enough swing points.
    """
    swing_highs, swing_lows = find_swing_points(candles)

    if len(swing_highs) < min_touches or len(swing_lows) < min_touches:
        return None

    slope_h, intercept_h, _r2_h = fit_trendline(swing_highs)
    slope_l, intercept_l, _r2_l = fit_trendline(swing_lows)

    n = len(candles)
    current_upper = slope_h * (n - 1) + intercept_h
    current_lower = slope_l * (n - 1) + intercept_l

    touch_upper = calculate_touch_points(candles, slope_h, intercept_h)
    touch_lower = calculate_touch_points(candles, slope_l, intercept_l)

    if len(touch_upper) < min_touches or len(touch_lower) < min_touches:
        return None

    upper = AlgoLine(
        color=LineColor.ORANGE,
        line_type=LineType.CHANNEL_UPPER,
        touch_points=touch_upper,
        slope=slope_h,
        current_level=current_upper,
        session_frequency=0.80,
    )
    lower = AlgoLine(
        color=LineColor.ORANGE,
        line_type=LineType.CHANNEL_LOWER,
        touch_points=touch_lower,
        slope=slope_l,
        current_level=current_lower,
        session_frequency=0.80,
    )
    return upper, lower


# ---------------------------------------------------------------------------
# Range-tapering (exhaustion) detection
# ---------------------------------------------------------------------------


def detect_tapering(candles: list[Candle], window: int = 20) -> bool:
    """Check if price range is narrowing (exhaustion / wedge forming).

    Compares average range of first half vs second half of window.
    Returns True when right-side ATR is less than 60% of left-side ATR.
    """
    if len(candles) < window:
        return False

    segment = candles[-window:]
    half = window // 2

    def _avg_range(bars: list[Candle]) -> float:
        return sum(c.high - c.low for c in bars) / len(bars) if bars else 0.0

    left_atr = _avg_range(segment[:half])
    right_atr = _avg_range(segment[half:])

    if left_atr == 0.0:
        return False
    return right_atr / left_atr < 0.60


# ---------------------------------------------------------------------------
# Per-color detection functions
# ---------------------------------------------------------------------------


def _detect_magenta(
    daily_candles: list[Candle],
    current_bar_index: int,
    tolerance_pct: float = 0.001,
) -> list[AlgoLine]:
    """P1 Magenta — Multi-day macro trendline from daily candles."""
    lines: list[AlgoLine] = []

    if len(daily_candles) < 5:
        return lines

    n = len(daily_candles)

    highs_pts = [(float(i), daily_candles[i].high) for i in range(n)]
    slope_h, intercept_h, _r2_h = fit_trendline(highs_pts)
    touches_h = calculate_touch_points(daily_candles, slope_h, intercept_h, tolerance_pct)

    if len(touches_h) >= 2:
        current_h = slope_h * (n - 1) + intercept_h
        line_type = (
            LineType.DESCENDING_RESISTANCE if slope_h < -0.0001
            else LineType.ASCENDING_SUPPORT if slope_h > 0.0001
            else LineType.HORIZONTAL
        )
        lines.append(
            AlgoLine(
                color=LineColor.MAGENTA,
                line_type=line_type,
                touch_points=touches_h,
                slope=slope_h,
                current_level=current_h,
                session_frequency=0.71,
            )
        )

    lows_pts = [(float(i), daily_candles[i].low) for i in range(n)]
    slope_l, intercept_l, _r2_l = fit_trendline(lows_pts)
    touches_l = calculate_touch_points(daily_candles, slope_l, intercept_l, tolerance_pct)

    if len(touches_l) >= 2:
        current_l = slope_l * (n - 1) + intercept_l
        line_type_l = (
            LineType.ASCENDING_SUPPORT if slope_l > 0.0001
            else LineType.DESCENDING_RESISTANCE if slope_l < -0.0001
            else LineType.HORIZONTAL
        )
        if line_type_l != lines[0].line_type if lines else True:
            lines.append(
                AlgoLine(
                    color=LineColor.MAGENTA,
                    line_type=line_type_l,
                    touch_points=touches_l,
                    slope=slope_l,
                    current_level=current_l,
                    session_frequency=0.71,
                )
            )

    return lines


def _detect_orange(
    intraday_candles: list[Candle],
    tolerance_pct: float = 0.001,
) -> list[AlgoLine]:
    """P2 Orange — Intraday channel from swing points."""
    lines: list[AlgoLine] = []

    if len(intraday_candles) < 15:
        return lines

    channel = detect_channel(intraday_candles)
    if channel:
        upper, lower = channel
        upper.color = LineColor.ORANGE
        lower.color = LineColor.ORANGE

        avg_slope = (upper.slope + lower.slope) / 2.0
        if abs(avg_slope) < 0.001:
            upper.line_type = LineType.HORIZONTAL
            lower.line_type = LineType.HORIZONTAL
        elif avg_slope > 0:
            upper.line_type = LineType.CHANNEL_UPPER
            lower.line_type = LineType.ASCENDING_SUPPORT
        else:
            upper.line_type = LineType.DESCENDING_RESISTANCE
            lower.line_type = LineType.CHANNEL_LOWER

        upper.session_frequency = 0.80
        lower.session_frequency = 0.80
        lines.append(upper)
        lines.append(lower)
    else:
        levels = find_horizontal_levels(intraday_candles, min_touches=2)
        for level in levels[:2]:
            touch_pts = calculate_touch_points(
                intraday_candles,
                slope=0.0,
                intercept=level,
                tolerance_pct=tolerance_pct * 2,
            )
            if len(touch_pts) >= 2:
                lines.append(
                    AlgoLine(
                        color=LineColor.ORANGE,
                        line_type=LineType.HORIZONTAL,
                        touch_points=touch_pts,
                        slope=0.0,
                        current_level=level,
                        session_frequency=0.80,
                    )
                )

    return lines


def _detect_green(
    intraday_candles: list[Candle],
    orange_lines: list[AlgoLine],
) -> list[AlgoLine]:
    """P3 Green — Continuation channel from recent portion of session."""
    lines: list[AlgoLine] = []

    if len(intraday_candles) < 20:
        return lines

    recent = intraday_candles[-min(90, len(intraday_candles)):]
    if len(recent) < 15:
        return lines

    breakout_detected = False
    if orange_lines:
        orange_upper = next(
            (
                ln for ln in orange_lines
                if ln.line_type in (LineType.CHANNEL_UPPER, LineType.DESCENDING_RESISTANCE)
            ),
            None,
        )
        if orange_upper and recent[-1].close > orange_upper.current_level:
            breakout_detected = True

    swing_highs, swing_lows = find_swing_points(recent, lookback=5)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return lines

    slope_h, intercept_h, _r2_h = fit_trendline(swing_highs)
    slope_l, intercept_l, _r2_l = fit_trendline(swing_lows)
    n = len(recent)

    touch_upper = calculate_touch_points(recent, slope_h, intercept_h)
    touch_lower = calculate_touch_points(recent, slope_l, intercept_l)

    if len(touch_upper) < 2 or len(touch_lower) < 2:
        return lines

    if slope_l > 0 or breakout_detected:
        lines.append(
            AlgoLine(
                color=LineColor.GREEN,
                line_type=LineType.CHANNEL_UPPER,
                touch_points=touch_upper,
                slope=slope_h,
                current_level=slope_h * (n - 1) + intercept_h,
                session_frequency=0.72,
            )
        )
        lines.append(
            AlgoLine(
                color=LineColor.GREEN,
                line_type=LineType.ASCENDING_SUPPORT,
                touch_points=touch_lower,
                slope=slope_l,
                current_level=slope_l * (n - 1) + intercept_l,
                session_frequency=0.72,
            )
        )
    elif slope_l >= -0.001 and slope_h >= -0.001:
        lines.append(
            AlgoLine(
                color=LineColor.GREEN,
                line_type=LineType.TRENDLINE,
                touch_points=touch_lower,
                slope=slope_l,
                current_level=slope_l * (n - 1) + intercept_l,
                session_frequency=0.72,
            )
        )

    return lines


def _detect_teal(intraday_candles: list[Candle]) -> list[AlgoLine]:
    """P4 Teal — Short-term counter-trend pullback lines (last 15-30 bars)."""
    lines: list[AlgoLine] = []

    if len(intraday_candles) < 15:
        return lines

    recent = intraday_candles[-min(30, len(intraday_candles)):]
    if len(recent) < 11:
        return lines

    swing_highs, swing_lows = find_swing_points(recent, lookback=3)

    if not swing_highs and not swing_lows:
        return lines

    half = len(recent) // 2
    first_half_close = sum(c.close for c in recent[:half]) / half
    second_half_close = sum(c.close for c in recent[half:]) / (len(recent) - half)
    local_uptrend = second_half_close > first_half_close

    if local_uptrend and len(swing_highs) >= 2:
        slope, intercept, _r2 = fit_trendline(swing_highs)
        n = len(recent)
        touches = calculate_touch_points(recent, slope, intercept)
        if len(touches) >= 2:
            lines.append(
                AlgoLine(
                    color=LineColor.TEAL,
                    line_type=LineType.DESCENDING_RESISTANCE,
                    touch_points=touches,
                    slope=slope,
                    current_level=slope * (n - 1) + intercept,
                    session_frequency=0.62,
                )
            )
    elif not local_uptrend and len(swing_lows) >= 2:
        slope, intercept, _r2 = fit_trendline(swing_lows)
        n = len(recent)
        touches = calculate_touch_points(recent, slope, intercept)
        if len(touches) >= 2:
            lines.append(
                AlgoLine(
                    color=LineColor.TEAL,
                    line_type=LineType.ASCENDING_SUPPORT,
                    touch_points=touches,
                    slope=slope,
                    current_level=slope * (n - 1) + intercept,
                    session_frequency=0.62,
                )
            )

    return lines


def _detect_yellow(
    daily_candles: list[Candle],
    intraday_candles: list[Candle],
    round_number_snap: float = 5.0,
    tolerance_pct: float = 0.001,
) -> list[AlgoLine]:
    """P5 Yellow — Macro horizontal S/R: prior-day pivots + round numbers."""
    lines: list[AlgoLine] = []

    if len(daily_candles) >= 2:
        prior_day = daily_candles[-2]
        key_levels = [prior_day.high, prior_day.low, prior_day.close]

        for level in key_levels:
            if level <= 0:
                continue
            touch_pts = calculate_touch_points(
                intraday_candles,
                slope=0.0,
                intercept=level,
                tolerance_pct=tolerance_pct * 2,
            ) if intraday_candles else [(0.0, level), (1.0, level)]

            if not touch_pts:
                touch_pts = [(daily_candles[-2].timestamp, level)]

            lines.append(
                AlgoLine(
                    color=LineColor.YELLOW,
                    line_type=LineType.HORIZONTAL,
                    touch_points=touch_pts if len(touch_pts) >= 1 else [(daily_candles[-2].timestamp, level)],
                    slope=0.0,
                    current_level=level,
                    session_frequency=0.60,
                )
            )

    if intraday_candles and round_number_snap > 0:
        current_price = intraday_candles[-1].close
        snap = round_number_snap
        round_near = round(current_price / snap) * snap
        round_next = (round(current_price / (snap * 2)) * snap * 2)
        for level in {round_near, round_next}:
            if level <= 0:
                continue
            touch_pts = calculate_touch_points(
                intraday_candles,
                slope=0.0,
                intercept=level,
                tolerance_pct=tolerance_pct * 3,
            )
            if len(touch_pts) >= 2:
                lines.append(
                    AlgoLine(
                        color=LineColor.YELLOW,
                        line_type=LineType.HORIZONTAL,
                        touch_points=touch_pts,
                        slope=0.0,
                        current_level=level,
                        session_frequency=0.60,
                    )
                )

    return lines


def _detect_pink(intraday_candles: list[Candle]) -> list[AlgoLine]:
    """P6 Pink — Cup rim / trigger: highest high before the current dip."""
    lines: list[AlgoLine] = []

    if len(intraday_candles) < 20:
        return lines

    n = len(intraday_candles)
    first_two_thirds = intraday_candles[: int(n * 2 / 3)]
    if not first_two_thirds:
        return lines

    rim_level = max(c.high for c in first_two_thirds)

    touch_pts = calculate_touch_points(
        intraday_candles,
        slope=0.0,
        intercept=rim_level,
        tolerance_pct=0.002,
    )

    if len(touch_pts) >= 1:
        lines.append(
            AlgoLine(
                color=LineColor.PINK,
                line_type=LineType.HORIZONTAL,
                touch_points=touch_pts,
                slope=0.0,
                current_level=rim_level,
                session_frequency=0.55,
            )
        )

    return lines


def _detect_blue(intraday_candles: list[Candle]) -> list[AlgoLine]:
    """P7 Blue — Exhaustion / tapering lines. Detects narrowing range."""
    lines: list[AlgoLine] = []

    if len(intraday_candles) < 20:
        return lines

    is_tapering = detect_tapering(intraday_candles)
    if not is_tapering:
        return lines

    segment = intraday_candles[-20:]
    swing_highs, swing_lows = find_swing_points(segment, lookback=3)

    if len(swing_highs) >= 2:
        slope_h, intercept_h, _ = fit_trendline(swing_highs)
        n = len(segment)
        touch_upper = calculate_touch_points(segment, slope_h, intercept_h)
        if len(touch_upper) >= 2:
            lines.append(
                AlgoLine(
                    color=LineColor.BLUE,
                    line_type=(
                        LineType.WEDGE_UPPER if slope_h < 0
                        else LineType.CHANNEL_UPPER
                    ),
                    touch_points=touch_upper,
                    slope=slope_h,
                    current_level=slope_h * (n - 1) + intercept_h,
                    session_frequency=0.50,
                )
            )

    if len(swing_lows) >= 2:
        slope_l, intercept_l, _ = fit_trendline(swing_lows)
        n = len(segment)
        touch_lower = calculate_touch_points(segment, slope_l, intercept_l)
        if len(touch_lower) >= 2:
            lines.append(
                AlgoLine(
                    color=LineColor.BLUE,
                    line_type=(
                        LineType.WEDGE_LOWER if slope_l > 0
                        else LineType.CHANNEL_LOWER
                    ),
                    touch_points=touch_lower,
                    slope=slope_l,
                    current_level=slope_l * (n - 1) + intercept_l,
                    session_frequency=0.50,
                )
            )

    return lines


# ---------------------------------------------------------------------------
# Main detector class
# ---------------------------------------------------------------------------


class LineDetector:
    """Detects all 7-color algorithm lines from multi-timeframe price data.

    Usage::

        detector = LineDetector(config)
        lines = detector.detect_lines(intraday, daily)
        # → list[AlgoLine] sorted P1 → P7
    """

    def __init__(self, config: AssetConfig | None = None) -> None:
        self.config = config if config is not None else get_config("SPY")

    def detect_lines(
        self,
        intraday_candles: list[Candle],
        daily_candles: list[Candle],
        prior_day_candles: list[Candle] | None = None,
    ) -> list[AlgoLine]:
        """Detect all active algorithm lines from price data.

        Args:
            intraday_candles:  Today's bars (oldest first).
            daily_candles:     Last 20+ daily bars (oldest first).
            prior_day_candles: Yesterday's bars (optional, unused directly).

        Returns:
            List of AlgoLine objects sorted by priority (P1 Magenta first).
        """
        tol = self.config.touch_tolerance_pct
        snap = self.config.round_number_snap

        all_lines: list[AlgoLine] = []

        magenta = _detect_magenta(daily_candles, len(intraday_candles), tol)
        all_lines.extend(magenta)

        orange = _detect_orange(intraday_candles, tol)
        all_lines.extend(orange)

        green = _detect_green(intraday_candles, orange)
        all_lines.extend(green)

        teal = _detect_teal(intraday_candles)
        all_lines.extend(teal)

        yellow = _detect_yellow(daily_candles, intraday_candles, snap, tol)
        all_lines.extend(yellow)

        pink = _detect_pink(intraday_candles)
        all_lines.extend(pink)

        blue = _detect_blue(intraday_candles)
        all_lines.extend(blue)

        priority_order = {
            LineColor.MAGENTA: 0,
            LineColor.ORANGE: 1,
            LineColor.GREEN: 2,
            LineColor.TEAL: 3,
            LineColor.YELLOW: 4,
            LineColor.PINK: 5,
            LineColor.BLUE: 6,
        }
        all_lines.sort(key=lambda ln: priority_order.get(ln.color, 99))
        return all_lines
