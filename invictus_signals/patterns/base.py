"""Base class for all pattern detectors.

Each entry pattern implements this ABC. Patterns are individually
testable and composable in the signal pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from invictus_signals.models import (
    AlgoLine,
    Candle,
    Direction,
    PatternMatch,
    RegimeClassification,
    TAState,
)


class PatternDetector(ABC):
    """Abstract base for entry pattern detection.

    Each pattern module implements detect() with specific IF/THEN logic.
    All conditions are measurable — shoulder symmetry, neckline breaks,
    volume thresholds, etc.
    """

    @property
    @abstractmethod
    def pattern_id(self) -> str:
        """Unique identifier, e.g. 'long_a_ihs', 'short_b_hs'."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name, e.g. 'Inverse Head & Shoulders'."""
        ...

    @property
    @abstractmethod
    def direction(self) -> Direction:
        """LONG or SHORT."""
        ...

    @property
    @abstractmethod
    def min_candles(self) -> int:
        """Minimum candle history required to detect this pattern."""
        ...

    @property
    @abstractmethod
    def frequency_pct(self) -> float:
        """Frequency in the dataset (e.g., 21.9 for iH&S)."""
        ...

    @abstractmethod
    def detect(
        self,
        candles: list[Candle],
        lines: list[AlgoLine],
        regime: RegimeClassification,
        ta_state: TAState,
    ) -> PatternMatch | None:
        """Detect pattern in current market state.

        Returns PatternMatch if pattern is detected with all conditions met,
        None otherwise. Must check:
        - Geometric conditions (shoulders, necklines, channels, etc.)
        - Volume confirmation (>= volume_multiplier × Vol MA)
        - Candle close beyond trigger (not just wick touch)
        - Regime alignment (no shorting intact uptrends, etc.)
        """
        ...

    def _check_volume(
        self,
        candle: Candle,
        ta_state: TAState,
        multiplier: float = 1.5,
    ) -> bool:
        """Check if candle volume meets the confirmation threshold."""
        return candle.volume >= ta_state.volume_ma * multiplier

    def _check_close_beyond(
        self,
        candle: Candle,
        level: float,
        direction: Direction,
    ) -> bool:
        """Check if candle closed beyond a price level."""
        if direction == Direction.LONG:
            return candle.close > level
        return candle.close < level
