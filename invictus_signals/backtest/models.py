"""Data models for the backtest / replay harness.

All money-touching fields use ``Decimal`` — never ``float``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from invictus_signals.models import Direction, RegimeId


@dataclass
class TradeResult:
    """Record of a single simulated trade produced by the fill model.

    R-multiple (``r_multiple``) is the signed profit divided by the risk:
    ``(exit_price - entry_price) / risk_per_unit`` for a LONG (negated for
    SHORT).  A full TP3 fill on a 1:3 trade yields ``r_multiple == Decimal(3)``.

    All price/R fields are ``Decimal`` to avoid float accumulation errors in
    P&L aggregation.
    """
    symbol: str
    pattern_id: str
    direction: Direction
    regime_id: RegimeId
    entry_price: Decimal
    exit_price: Decimal
    stop_price: Decimal
    target_prices: list[Decimal]        # TP1/TP2/TP3 ladder
    fees_paid: Decimal                  # Taker fee both legs (entry + exit)
    r_multiple: Decimal                 # Signed R (positive = win, negative = loss)
    exit_reason: str                    # "tp1" | "tp2" | "tp3" | "sl" | "end_of_data"
    bar_index: int                      # Which bar in the replay this trade entered
    timestamp: float


@dataclass
class RegimePatternKey:
    """Composite key for the per-(pattern, regime) matrix."""
    pattern_id: str
    regime_id: RegimeId


@dataclass
class AggregateStats:
    """Aggregated trade statistics for a symbol or (pattern, regime) bucket.

    Win/loss/break-even contract (matches the live /performance matrix):
      - win:        net r_multiple > 0  (positive after fees)
      - loss:       net r_multiple < 0  (negative after fees)
      - break_even: net r_multiple == 0 (rare; fee-eroded stop exits can land here)

    All three are counted independently; ``trades == wins + losses + break_even``.
    """
    trades: int = 0
    wins: int = 0
    losses: int = 0
    break_even: int = 0
    total_r: Decimal = field(default_factory=lambda: Decimal(0))
    total_fees: Decimal = field(default_factory=lambda: Decimal(0))

    @property
    def win_rate(self) -> Decimal:
        """Win rate as a fraction [0, 1].  Returns 0 for empty buckets."""
        if self.trades == 0:
            return Decimal(0)
        return Decimal(self.wins) / Decimal(self.trades)

    @property
    def avg_r(self) -> Decimal:
        """Average R-multiple per trade.  Returns 0 for empty buckets."""
        if self.trades == 0:
            return Decimal(0)
        return self.total_r / Decimal(self.trades)


@dataclass
class BacktestReport:
    """Full replay output — mirrors the live /performance matrix shape.

    ``per_symbol``         -- AggregateStats keyed by symbol string.
    ``per_pattern_regime`` -- AggregateStats keyed by (pattern_id, regime_id.value).
    ``all_trades``         -- flat list of every TradeResult (inspect / export).
    """
    per_symbol: dict[str, AggregateStats] = field(default_factory=dict)
    per_pattern_regime: dict[tuple[str, str], AggregateStats] = field(default_factory=dict)
    all_trades: list[TradeResult] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        """Compact summary dict suitable for logging or test assertions.

        Win/loss/break_even contract mirrors AggregateStats:
          win = net r_multiple > 0, loss = r_multiple < 0, break_even = r_multiple == 0.
        """
        total = AggregateStats()
        for t in self.all_trades:
            total.trades += 1
            if t.r_multiple > Decimal(0):
                total.wins += 1
            elif t.r_multiple < Decimal(0):
                total.losses += 1
            else:
                total.break_even += 1
            total.total_r += t.r_multiple
            total.total_fees += t.fees_paid
        return {
            "total_trades": total.trades,
            "wins": total.wins,
            "losses": total.losses,
            "break_even": total.break_even,
            "win_rate": float(total.win_rate),
            "avg_r": float(total.avg_r),
            "total_r": float(total.total_r),
            "total_fees": float(total.total_fees),
        }
