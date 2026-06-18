"""Regime-label validation: replay vs. reference sample.

``validate_regime_labels`` compares regime IDs produced by the replay engine
against a ground-truth reference set (e.g. a ``trades.db`` export).  This is
purely offline — the reference is passed as a Python list, no DB connection.

Target: >= 95% match rate (measured as an exact regime_id string equality on
matched (symbol, timestamp) pairs).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from invictus_signals.config import AssetConfig, get_config
from invictus_signals.models import Candle
from invictus_signals.regime_classifier import classify_regime
from invictus_signals.ta_engine import compute_ta_state
from invictus_signals.backtest.engine import _MIN_WARMUP_BARS


@dataclass
class ReferenceRow:
    """Single ground-truth regime label from a reference source.

    Matches a bar by ``(symbol, timestamp)`` — same fields the engine would
    compute at that point in time.

    Args:
        symbol: Asset symbol string.
        timestamp: Bar timestamp (float epoch seconds, matching ``Candle.timestamp``).
        regime_id: Expected regime_id string (e.g. ``"b1_trending"``).
    """
    symbol: str
    timestamp: float
    regime_id: str


@dataclass
class ValidationReport:
    """Output of ``validate_regime_labels``.

    Attributes:
        total_checked: Number of reference rows for which a matching bar was found.
        matched: Number where replay regime == reference regime.
        match_rate: ``matched / total_checked`` — target >= 0.95.
        mismatches: List of dicts describing each mismatch
            ``{"symbol", "timestamp", "expected", "actual"}``.
        skipped: Rows where no matching bar was found in the provided candles.
    """
    total_checked: int
    matched: int
    match_rate: float
    mismatches: list[dict[str, str | float]]
    skipped: int

    @property
    def passes_threshold(self) -> bool:
        """True when match_rate >= 95%."""
        return self.match_rate >= 0.95


def validate_regime_labels(
    candles_by_symbol: dict[str, Sequence[Candle]],
    intraday_by_symbol: dict[str, Sequence[Candle]],
    reference: Sequence[ReferenceRow],
    asset_configs: dict[str, AssetConfig] | None = None,
) -> ValidationReport:
    """Validate replay-computed regime labels against a reference sample.

    For each ``ReferenceRow`` the function:
    1. Looks up the daily + intraday candles for that symbol.
    2. Finds the bar whose ``timestamp`` matches ``row.timestamp`` (within
       the provided candle series).
    3. Recomputes ``TAState`` + ``RegimeClassification`` using the same
       pure functions as the live engine.
    4. Compares the resulting ``regime_id.value`` to ``row.regime_id``.

    No network access, no DB connection.  Pass the reference as a plain list.

    Args:
        candles_by_symbol: Daily candle history per symbol (most-recent last).
        intraday_by_symbol: Intraday candle history per symbol.
        reference: Ground-truth sample rows.
        asset_configs: Optional per-symbol ``AssetConfig`` overrides.

    Returns:
        ``ValidationReport`` with match_rate, mismatches, and skipped count.
    """
    if asset_configs is None:
        asset_configs = {}

    # Build timestamp → bar index lookup per symbol
    ts_index: dict[str, dict[float, int]] = {}
    for sym, bars in candles_by_symbol.items():
        ts_index[sym] = {b.timestamp: i for i, b in enumerate(bars)}

    matched = 0
    mismatches: list[dict[str, str | float]] = []
    skipped = 0

    for row in reference:
        sym = row.symbol
        daily_bars = candles_by_symbol.get(sym)
        intraday_bars = intraday_by_symbol.get(sym)

        if daily_bars is None or intraday_bars is None:
            skipped += 1
            continue

        sym_ts_index = ts_index.get(sym, {})
        bar_idx = sym_ts_index.get(row.timestamp)
        if bar_idx is None or bar_idx < _MIN_WARMUP_BARS:
            # Not enough preceding bars for TA computation — skip to match
            # the same gate the replay engine applies (30-bar warmup floor).
            skipped += 1
            continue

        cfg = asset_configs.get(sym)
        if cfg is None:
            try:
                cfg = get_config(sym)
            except KeyError:
                cfg = get_config("SPY")

        try:
            ta = compute_ta_state(intraday_bars, list(daily_bars[: bar_idx + 1]), cfg)
        except ValueError:
            skipped += 1
            continue

        replay_regime = classify_regime(
            ta,
            current_price=daily_bars[bar_idx].close,
            config=cfg,
        )
        replay_id = replay_regime.regime_id.value

        if replay_id == row.regime_id:
            matched += 1
        else:
            mismatches.append(
                {
                    "symbol": sym,
                    "timestamp": row.timestamp,
                    "expected": row.regime_id,
                    "actual": replay_id,
                }
            )

    total_checked = matched + len(mismatches)
    match_rate = matched / total_checked if total_checked > 0 else 0.0

    return ValidationReport(
        total_checked=total_checked,
        matched=matched,
        match_rate=match_rate,
        mismatches=mismatches,
        skipped=skipped,
    )
