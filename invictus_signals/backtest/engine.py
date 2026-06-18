"""Offline replay engine for invictus-signals.

Architecture / seam
-------------------
Pattern detection lives in the BOT, not in invictus-signals.  This engine
therefore accepts pattern intent via an INJECTABLE CALLBACK:

    pattern_fn(ta_state: TAState, lines: list[AlgoLine])
        -> Optional[tuple[str, Direction]]

  - Returns ``(pattern_id, direction)`` when a signal fires on this bar.
  - Returns ``None`` when no signal fires.
  - May be replaced with a precomputed signal stream using
    ``SignalRecord`` items passed to ``ReplayEngine`` instead.

This keeps the harness fully usable without importing the bot.

Fill model
----------
On a ``pattern_fn`` signal at bar N the engine:
  1. Records entry at bar N+1 open (next-bar fill).
  2. Walks subsequent bars until the first of:
     - SL hit (bar low <= SL for LONG / bar high >= SL for SHORT)
     - TP1/TP2/TP3 hit in sequence (partial fills at each TP)
     - End of data
  3. Charges taker fee (``fee_rate``) on entry notional + exit notional.

Ladder
------
TP targets come from ``BacktestConfig.tp_r_multiples`` (default [1.0, 2.0, 3.0]).
Exit price is the TP that was hit; a full stop is at R = -1.0 net of fees.

Pure / offline guarantee
------------------------
No network, no exchange calls, no order placement anywhere in this module.
All inputs are plain Python objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Optional, Sequence

from invictus_signals.config import AssetConfig, get_config
from invictus_signals.models import (
    AlgoLine,
    Candle,
    Direction,
    RegimeClassification,
    TAState,
)
from invictus_signals.regime_classifier import classify_regime
from invictus_signals.ta_engine import compute_ta_state
from invictus_signals.backtest.models import (
    AggregateStats,
    BacktestReport,
    TradeResult,
)

# Callable type alias — injected from the bot or test stubs.
PatternFn = Callable[
    [TAState, list[AlgoLine]],
    Optional[tuple[str, Direction]],
]

# Minimal warmup: enough bars for all indicators (slow MA + BB + slope).
_MIN_WARMUP_BARS = 30


def _decimal(value: float) -> Decimal:
    """Convert a float to Decimal using half-up rounding to 8dp."""
    return Decimal(str(value)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


@dataclass
class BacktestConfig:
    """Configuration for a single replay run.

    Args:
        symbol: Asset symbol string (used to pick ``AssetConfig`` preset).
        risk_per_unit: Fractional distance from entry to SL as a fraction of
            entry price (e.g. 0.01 = 1% stop).  Used to compute TP levels
            and absolute R.
        tp_r_multiples: R-multiple targets for the ladder [TP1, TP2, TP3].
            Default mirrors the live 1:1:2:3 bracket.
        fee_rate: Taker fee rate (fraction of notional) per leg.  Default
            matches Phemex taker fee of 0.06%.
        asset_config: Override the ``AssetConfig`` preset.  Defaults to
            ``get_config(symbol)`` — falls back to SPY if symbol unknown.
    """
    symbol: str = "BTC"
    risk_per_unit: Decimal = field(default_factory=lambda: Decimal("0.01"))
    tp_r_multiples: list[Decimal] = field(
        default_factory=lambda: [Decimal("1"), Decimal("2"), Decimal("3")]
    )
    fee_rate: Decimal = field(default_factory=lambda: Decimal("0.0006"))
    asset_config: AssetConfig | None = None

    def resolved_asset_config(self) -> AssetConfig:
        if self.asset_config is not None:
            return self.asset_config
        try:
            return get_config(self.symbol)
        except KeyError:
            return get_config("SPY")


def _compute_tp_levels(
    entry: Decimal,
    sl: Decimal,
    direction: Direction,
    tp_r_multiples: list[Decimal],
) -> list[Decimal]:
    """Return TP price levels from an entry/SL pair and R-multiple ladder."""
    risk = abs(entry - sl)
    result = []
    for mult in tp_r_multiples:
        if direction == Direction.LONG:
            result.append(entry + risk * mult)
        else:
            result.append(entry - risk * mult)
    return result


def _fill_trade(
    bars: Sequence[Candle],
    start_idx: int,
    entry: Decimal,
    sl: Decimal,
    tp_levels: list[Decimal],
    direction: Direction,
    fee_rate: Decimal,
    symbol: str,
    pattern_id: str,
    timestamp: float,
    regime_classification: RegimeClassification,
) -> Optional[TradeResult]:
    """Walk bars from ``start_idx`` and return the first exit encountered.

    Returns None if ``start_idx`` is out of range (insufficient bars after
    the signal — caller skips gracefully).
    """
    if start_idx >= len(bars):
        return None

    risk = abs(entry - sl)
    if risk == Decimal(0):
        return None  # Degenerate: no risk defined, skip

    # Iterate through bars starting at next bar after signal.
    for idx in range(start_idx, len(bars)):
        bar = bars[idx]
        bar_high = _decimal(bar.high)
        bar_low = _decimal(bar.low)
        bar_close = _decimal(bar.close)

        if direction == Direction.LONG:
            # Check SL first (conservative)
            if bar_low <= sl:
                exit_price = sl
                r = (exit_price - entry) / risk  # negative: sl < entry for LONG
                fees = (entry + exit_price) * fee_rate
                return TradeResult(
                    symbol=symbol,
                    pattern_id=pattern_id,
                    direction=direction,
                    regime_id=regime_classification.regime_id,
                    entry_price=entry,
                    exit_price=exit_price,
                    stop_price=sl,
                    target_prices=tp_levels,
                    fees_paid=fees,
                    r_multiple=r - fees / risk,
                    exit_reason="sl",
                    bar_index=idx,
                    timestamp=bar.timestamp,
                )
            # Check TPs in order
            for tp_idx, tp in enumerate(tp_levels):
                if bar_high >= tp:
                    exit_price = tp
                    r = (exit_price - entry) / risk
                    fees = (entry + exit_price) * fee_rate
                    return TradeResult(
                        symbol=symbol,
                        pattern_id=pattern_id,
                        direction=direction,
                        regime_id=regime_classification.regime_id,
                        entry_price=entry,
                        exit_price=exit_price,
                        stop_price=sl,
                        target_prices=tp_levels,
                        fees_paid=fees,
                        r_multiple=r - fees / risk,
                        exit_reason=f"tp{tp_idx + 1}",
                        bar_index=idx,
                        timestamp=bar.timestamp,
                    )
        else:  # SHORT
            # Check SL first
            if bar_high >= sl:
                exit_price = sl
                r = (entry - exit_price) / risk
                fees = (entry + exit_price) * fee_rate
                return TradeResult(
                    symbol=symbol,
                    pattern_id=pattern_id,
                    direction=direction,
                    regime_id=regime_classification.regime_id,
                    entry_price=entry,
                    exit_price=exit_price,
                    stop_price=sl,
                    target_prices=tp_levels,
                    fees_paid=fees,
                    r_multiple=r - fees / risk,
                    exit_reason="sl",
                    bar_index=idx,
                    timestamp=bar.timestamp,
                )
            for tp_idx, tp in enumerate(tp_levels):
                if bar_low <= tp:
                    exit_price = tp
                    r = (entry - exit_price) / risk
                    fees = (entry + exit_price) * fee_rate
                    return TradeResult(
                        symbol=symbol,
                        pattern_id=pattern_id,
                        direction=direction,
                        regime_id=regime_classification.regime_id,
                        entry_price=entry,
                        exit_price=exit_price,
                        stop_price=sl,
                        target_prices=tp_levels,
                        fees_paid=fees,
                        r_multiple=r - fees / risk,
                        exit_reason=f"tp{tp_idx + 1}",
                        bar_index=idx,
                        timestamp=bar.timestamp,
                    )

    # End of data — exit at last bar close
    last = bars[-1]
    exit_price = _decimal(last.close)
    if direction == Direction.LONG:
        r = (exit_price - entry) / risk
    else:
        r = (entry - exit_price) / risk
    fees = (entry + exit_price) * fee_rate
    return TradeResult(
        symbol=symbol,
        pattern_id=pattern_id,
        direction=direction,
        regime_id=regime_classification.regime_id,
        entry_price=entry,
        exit_price=exit_price,
        stop_price=sl,
        target_prices=tp_levels,
        fees_paid=fees,
        r_multiple=r - fees / risk,
        exit_reason="end_of_data",
        bar_index=len(bars) - 1,
        timestamp=last.timestamp,
    )


def _classify_outcome(r: Decimal) -> tuple[int, int, int]:
    """Return (wins, losses, break_even) increments for a single trade R."""
    if r > Decimal(0):
        return (1, 0, 0)
    if r < Decimal(0):
        return (0, 1, 0)
    return (0, 0, 1)


def _update_stats(
    report: BacktestReport,
    trade: TradeResult,
    symbol: str,
) -> None:
    """Mutate ``report`` in-place to record a trade."""
    w, l, b = _classify_outcome(trade.r_multiple)

    # Per-symbol bucket
    if symbol not in report.per_symbol:
        report.per_symbol[symbol] = AggregateStats()
    sym_bucket = report.per_symbol[symbol]
    sym_bucket.trades += 1
    sym_bucket.wins += w
    sym_bucket.losses += l
    sym_bucket.break_even += b
    sym_bucket.total_r += trade.r_multiple
    sym_bucket.total_fees += trade.fees_paid

    # Per-(pattern, regime) bucket
    key = (trade.pattern_id, trade.regime_id.value)
    if key not in report.per_pattern_regime:
        report.per_pattern_regime[key] = AggregateStats()
    pr_bucket = report.per_pattern_regime[key]
    pr_bucket.trades += 1
    pr_bucket.wins += w
    pr_bucket.losses += l
    pr_bucket.break_even += b
    pr_bucket.total_r += trade.r_multiple
    pr_bucket.total_fees += trade.fees_paid


@dataclass
class SignalRecord:
    """Precomputed signal — alternative to the ``pattern_fn`` callback.

    When the caller has a trades-db export or a precomputed signal stream,
    they can inject it as a list of ``SignalRecord`` objects keyed by bar
    index.  ``ReplayEngine`` uses these instead of calling ``pattern_fn``.
    """
    bar_index: int
    pattern_id: str
    direction: Direction
    stop_offset_pct: float  # Fraction of bar close used as SL distance


class ReplayEngine:
    """Deterministic offline replay engine.

    Usage
    -----
    ::

        engine = ReplayEngine(
            daily_candles=my_daily_bars,
            intraday_candles=my_intraday_bars,
            config=BacktestConfig(symbol="BTC"),
            pattern_fn=my_pattern_detector,   # or pass signals= instead
        )
        report = engine.run()

    The ``pattern_fn`` is called on every bar where sufficient warmup data
    exists.  It receives the current ``TAState`` and an empty list of lines
    (line detection is also bot-side; pass lines via a wrapper closure if
    available).

    Alternatively, pass ``signals`` — a list of ``SignalRecord`` objects —
    to replay a pre-recorded signal stream without a live callback.  If both
    are provided, ``signals`` takes precedence.
    """

    def __init__(
        self,
        daily_candles: Sequence[Candle],
        intraday_candles: Sequence[Candle],
        config: BacktestConfig,
        pattern_fn: PatternFn | None = None,
        signals: list[SignalRecord] | None = None,
    ) -> None:
        """Initialise the engine.

        Args:
            daily_candles: Full daily OHLCV history (most-recent last).
            intraday_candles: Intraday bars for the same period (most-recent
                last).  Must be non-empty.
            config: ``BacktestConfig`` controlling fees, risk, and TP ladder.
            pattern_fn: Optional injectable pattern callback.  Called once
                per bar after warmup; returns ``(pattern_id, direction)`` or
                None.
            signals: Optional precomputed signal list (see ``SignalRecord``).
                Takes precedence over ``pattern_fn`` when provided.
        """
        if not daily_candles:
            raise ValueError("daily_candles must not be empty")
        if not intraday_candles:
            raise ValueError("intraday_candles must not be empty")
        if pattern_fn is None and not signals:
            raise ValueError(
                "Provide either pattern_fn or signals — at least one is required"
            )
        self._daily = list(daily_candles)
        self._intraday = list(intraday_candles)
        self._config = config
        self._pattern_fn = pattern_fn
        # Build a bar-index → signal map for O(1) lookup
        self._signal_map: dict[int, SignalRecord] = {}
        if signals:
            for sig in signals:
                self._signal_map[sig.bar_index] = sig

    def run(self) -> BacktestReport:
        """Run the full replay and return the aggregated ``BacktestReport``.

        Returns:
            A ``BacktestReport`` with per-symbol, per-(pattern,regime), and
            all-trades data.  An empty report is returned when there is
            insufficient warmup data.
        """
        report = BacktestReport()
        cfg = self._config
        asset_cfg = cfg.resolved_asset_config()
        symbol = cfg.symbol
        n = len(self._daily)

        if n < _MIN_WARMUP_BARS:
            # Not enough bars for any indicator — return empty report
            return report

        # Walk each bar after warmup
        for i in range(_MIN_WARMUP_BARS, n):
            daily_window = self._daily[: i + 1]
            # Use the full intraday candle list as a proxy for session data.
            # In production the bot slices per-day; for backtesting we pass
            # the full intraday series so TA state is consistent.
            try:
                ta = compute_ta_state(self._intraday, daily_window, asset_cfg)
            except ValueError:
                continue

            regime: RegimeClassification = classify_regime(
                ta,
                current_price=self._daily[i].close,
                config=asset_cfg,
            )

            # Determine signal: precomputed map takes precedence.
            signal: Optional[tuple[str, Direction]] = None
            if i in self._signal_map:
                sig_rec = self._signal_map[i]
                signal = (sig_rec.pattern_id, sig_rec.direction)
                # Override risk_per_unit for this specific signal
                sig_risk = _decimal(sig_rec.stop_offset_pct)
            else:
                sig_risk = cfg.risk_per_unit
                if self._pattern_fn is not None:
                    signal = self._pattern_fn(ta, [])

            if signal is None:
                continue

            pattern_id, direction = signal
            # Next-bar fill — entry at next bar open
            if i + 1 >= n:
                continue
            next_bar = self._daily[i + 1]
            entry = _decimal(next_bar.open)
            if entry == Decimal(0):
                continue

            # SL placement: entry ± risk_per_unit of entry
            if direction == Direction.LONG:
                sl = entry * (Decimal(1) - sig_risk)
            else:
                sl = entry * (Decimal(1) + sig_risk)

            tp_levels = _compute_tp_levels(entry, sl, direction, cfg.tp_r_multiples)

            trade = _fill_trade(
                bars=self._daily,
                start_idx=i + 1,
                entry=entry,
                sl=sl,
                tp_levels=tp_levels,
                direction=direction,
                fee_rate=cfg.fee_rate,
                symbol=symbol,
                pattern_id=pattern_id,
                timestamp=next_bar.timestamp,
                regime_classification=regime,
            )
            if trade is None:
                continue

            report.all_trades.append(trade)
            _update_stats(report, trade, symbol)

        return report
