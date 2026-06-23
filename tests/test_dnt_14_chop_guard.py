"""Tests for dnt_14_weak_intraday_trend — the 1H trend-strength chop guard."""
from invictus_signals.dnt_filters import dnt_14_weak_intraday_trend
from invictus_signals.models import TAState


def _ta(intraday_adx: float) -> TAState:
    """Minimal TAState with a given intraday ADX (other fields irrelevant here)."""
    return TAState(
        ma_fast=100.0, ma_mid=100.0, ma_slow=100.0,
        ma_fast_slope=0.0, ma_mid_slope=0.0,
        bb_upper=101.0, bb_lower=99.0, bb_middle=100.0,
        bb_width=0.02, bb_upper_slope=0.0,
        volume_ma=1000.0, vwap=100.0,
        intraday_adx=intraday_adx,
    )


def test_weak_intraday_trend_triggers_in_chop():
    """1H ADX below threshold => veto the entry (choppy entry timeframe)."""
    result = dnt_14_weak_intraday_trend(_ta(15.0), min_intraday_adx=35.0)
    assert result.triggered is True
    assert result.filter_id == "dnt_14_weak_intraday_trend"


def test_strong_intraday_trend_passes():
    """1H ADX at/above threshold => allow the entry (trend present)."""
    assert dnt_14_weak_intraday_trend(_ta(45.0), min_intraday_adx=35.0).triggered is False
    # exactly at threshold is allowed (strict <)
    assert dnt_14_weak_intraday_trend(_ta(35.0), min_intraday_adx=35.0).triggered is False


def test_default_threshold_is_35():
    """The bare-function default must match the production AssetConfig (35.0),
    so a direct caller can never silently diverge from the tuned value."""
    assert dnt_14_weak_intraday_trend(_ta(34.0)).triggered is True   # 34 < 35
    assert dnt_14_weak_intraday_trend(_ta(36.0)).triggered is False  # 36 >= 35


def test_absent_intraday_adx_fails_open():
    """0.0 is the 'no intraday data' sentinel — must NOT trigger (warmup-safe)."""
    assert dnt_14_weak_intraday_trend(_ta(0.0), min_intraday_adx=35.0).triggered is False


def test_negative_intraday_adx_fails_open():
    """Defensive: a negative ADX (cannot occur from calculate_adx, but a hand-
    built TAState could) is treated like the absent sentinel — fails open."""
    assert dnt_14_weak_intraday_trend(_ta(-5.0), min_intraday_adx=35.0).triggered is False


def test_threshold_is_honored():
    """A lower threshold lets more (weaker) trends through."""
    assert dnt_14_weak_intraday_trend(_ta(22.0), min_intraday_adx=35.0).triggered is True
    assert dnt_14_weak_intraday_trend(_ta(22.0), min_intraday_adx=20.0).triggered is False
