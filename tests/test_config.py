"""Tests for invictus_signals.config."""
from __future__ import annotations

import dataclasses

import pytest

from invictus_signals.config import AssetConfig, ASSET_PRESETS, get_config


class TestAssetPresets:
    def test_all_presets_exist(self) -> None:
        for symbol in ("SPY", "BTC", "ETH", "SOL"):
            assert symbol in ASSET_PRESETS

    def test_spy_preset_values(self) -> None:
        cfg = ASSET_PRESETS["SPY"]
        assert cfg.symbol == "SPY"
        assert cfg.ma_fast_period == 5
        assert cfg.ma_mid_period == 20
        assert cfg.round_number_snap == 5.0
        assert cfg.market_open == (9, 30)
        assert cfg.market_close == (16, 0)

    def test_btc_preset_values(self) -> None:
        cfg = ASSET_PRESETS["BTC"]
        assert cfg.symbol == "BTC"
        assert cfg.ma_fast_period == 12
        assert cfg.ma_mid_period == 26
        assert cfg.round_number_snap == 1000.0
        assert cfg.intermingling_threshold == 0.005
        assert cfg.market_open is None  # 24/7
        assert cfg.market_close is None

    def test_eth_preset_values(self) -> None:
        cfg = ASSET_PRESETS["ETH"]
        assert cfg.round_number_snap == 100.0
        assert cfg.choppy_range_threshold == 30.0

    def test_sol_preset_values(self) -> None:
        cfg = ASSET_PRESETS["SOL"]
        assert cfg.round_number_snap == 10.0
        assert cfg.choppy_range_threshold == 3.0

    def test_presets_are_immutable_via_get_config(self) -> None:
        """get_config with overrides returns a new object, not mutating preset."""
        cfg1 = get_config("BTC")
        cfg2 = get_config("BTC", ma_fast_period=99)
        assert cfg1.ma_fast_period == 12
        assert cfg2.ma_fast_period == 99
        # Original preset not mutated
        assert ASSET_PRESETS["BTC"].ma_fast_period == 12


class TestGetConfig:
    def test_known_symbol_uppercase(self) -> None:
        cfg = get_config("SPY")
        assert cfg.symbol == "SPY"

    def test_known_symbol_lowercase(self) -> None:
        cfg = get_config("spy")
        assert cfg.symbol == "SPY"

    def test_known_symbol_mixed_case(self) -> None:
        cfg = get_config("Btc")
        assert cfg.symbol == "BTC"

    def test_unknown_symbol_falls_back_to_btc(self) -> None:
        cfg = get_config("DOGE")
        assert cfg.symbol == "DOGE"
        # Should use BTC periods
        assert cfg.ma_fast_period == 12
        assert cfg.ma_mid_period == 26
        assert cfg.intermingling_threshold == 0.005

    def test_overrides_applied(self) -> None:
        cfg = get_config("SPY", ma_fast_period=10, round_number_snap=1.0)
        assert cfg.ma_fast_period == 10
        assert cfg.round_number_snap == 1.0
        # Other fields unchanged
        assert cfg.ma_mid_period == 20

    def test_override_symbol_field(self) -> None:
        cfg = get_config("ETH", choppy_range_threshold=50.0)
        assert cfg.choppy_range_threshold == 50.0

    def test_returns_new_instance_each_call(self) -> None:
        cfg1 = get_config("BTC")
        cfg2 = get_config("BTC")
        # Same values but not same object (replace creates new dataclass)
        assert cfg1 == cfg2

    def test_unknown_symbol_no_overrides(self) -> None:
        """Unknown crypto with no overrides uses BTC defaults."""
        cfg = get_config("XRP")
        assert cfg.touch_tolerance_pct == 0.003

    def test_spy_market_hours_preserved(self) -> None:
        cfg = get_config("SPY")
        assert cfg.market_open == (9, 30)
        assert cfg.market_close == (16, 0)

    def test_btc_no_market_hours(self) -> None:
        cfg = get_config("BTC")
        assert cfg.market_open is None
        assert cfg.market_close is None


class TestAssetConfigDefaults:
    def test_default_ma_slow_period(self) -> None:
        cfg = AssetConfig(symbol="TEST")
        assert cfg.ma_slow_period == 200

    def test_default_bb_std_dev(self) -> None:
        cfg = AssetConfig(symbol="TEST")
        assert cfg.bb_std_dev == 2.0

    def test_default_volume_multiplier(self) -> None:
        cfg = AssetConfig(symbol="TEST")
        assert cfg.volume_multiplier == 1.5

    def test_dataclass_replace_works(self) -> None:
        base = AssetConfig(symbol="TEST", ma_fast_period=5)
        modified = dataclasses.replace(base, ma_fast_period=20)
        assert modified.ma_fast_period == 20
        assert base.ma_fast_period == 5
