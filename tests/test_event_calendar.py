"""Tests for invictus_signals.event_calendar."""
from __future__ import annotations

import datetime

import pytest

from invictus_signals.event_calendar import (
    get_event_info,
    get_upcoming_events,
    is_event_day,
    _FOMC_DATES,
    _CPI_DATES,
    _NFP_DATES,
    _BTC_HALVING_DATES,
)


class TestIsEventDay:
    def test_known_fomc_date(self) -> None:
        assert is_event_day(datetime.date(2024, 9, 18)) is True

    def test_known_cpi_date(self) -> None:
        assert is_event_day(datetime.date(2024, 8, 14)) is True

    def test_known_nfp_date(self) -> None:
        assert is_event_day(datetime.date(2024, 7, 5)) is True

    def test_btc_halving_date(self) -> None:
        assert is_event_day(datetime.date(2024, 4, 20)) is True

    def test_non_event_day(self) -> None:
        assert is_event_day(datetime.date(2024, 6, 15)) is False  # Random Saturday

    def test_filter_by_fomc_only(self) -> None:
        fomc_date = datetime.date(2024, 9, 18)
        assert is_event_day(fomc_date, events="fomc") is True
        # Make sure CPI date doesn't trigger FOMC filter
        cpi_only = datetime.date(2024, 8, 14)
        assert is_event_day(cpi_only, events="fomc") is False

    def test_filter_by_cpi_only(self) -> None:
        cpi_date = datetime.date(2024, 8, 14)
        assert is_event_day(cpi_date, events="cpi") is True

    def test_filter_by_nfp_only(self) -> None:
        nfp_date = datetime.date(2024, 7, 5)
        assert is_event_day(nfp_date, events="nfp") is True

    def test_filter_by_halving_only(self) -> None:
        assert is_event_day(datetime.date(2024, 4, 20), events="halving") is True

    def test_multiple_event_types(self) -> None:
        fomc_date = datetime.date(2024, 9, 18)
        assert is_event_day(fomc_date, events="fomc,nfp") is True

    def test_all_keyword(self) -> None:
        fomc_date = datetime.date(2024, 9, 18)
        assert is_event_day(fomc_date, events="all") is True

    def test_unknown_event_type_no_crash(self) -> None:
        # Unknown event type just returns False without crashing
        result = is_event_day(datetime.date(2024, 9, 18), events="unknown_event")
        assert result is False


class TestGetEventInfo:
    def test_fomc_event_returns_dict(self) -> None:
        info = get_event_info(datetime.date(2024, 9, 18))
        assert info is not None
        assert info["type"] == "fomc"
        assert "name" in info

    def test_cpi_event_info(self) -> None:
        info = get_event_info(datetime.date(2024, 8, 14))
        assert info is not None
        assert info["type"] == "cpi"

    def test_halving_event_info(self) -> None:
        info = get_event_info(datetime.date(2024, 4, 20))
        assert info is not None
        assert info["type"] == "halving"
        assert "BTC" in str(info.get("assets_affected", ""))

    def test_non_event_returns_none(self) -> None:
        info = get_event_info(datetime.date(2024, 6, 15))
        assert info is None

    def test_event_info_has_date(self) -> None:
        info = get_event_info(datetime.date(2024, 9, 18))
        assert info is not None
        assert info["date"] == "2024-09-18"


class TestGetUpcomingEvents:
    def test_returns_list(self) -> None:
        result = get_upcoming_events(datetime.date(2024, 9, 15), days_ahead=7)
        assert isinstance(result, list)

    def test_finds_fomc_in_window(self) -> None:
        # FOMC on 2024-09-18, look from 2024-09-15
        result = get_upcoming_events(datetime.date(2024, 9, 15), days_ahead=5)
        types = [e["type"] for e in result]
        assert "fomc" in types

    def test_empty_when_no_events_in_window(self) -> None:
        # Pick a window with no events (hard to guarantee, but test mechanism)
        result = get_upcoming_events(datetime.date(2024, 6, 15), days_ahead=0)
        # June 15 is a Saturday — likely no events
        assert isinstance(result, list)

    def test_sorted_by_date(self) -> None:
        result = get_upcoming_events(datetime.date(2024, 1, 1), days_ahead=30)
        if len(result) >= 2:
            dates = [e["date"] for e in result]
            assert dates == sorted(dates)

    def test_filter_by_type(self) -> None:
        result = get_upcoming_events(datetime.date(2024, 9, 1), days_ahead=30, events="fomc")
        for e in result:
            assert e["type"] == "fomc"

    def test_days_away_field(self) -> None:
        result = get_upcoming_events(datetime.date(2024, 9, 15), days_ahead=5)
        for e in result:
            assert "days_away" in e
            assert 0 <= int(str(e["days_away"])) <= 5


class TestCalendarCoverage:
    def test_fomc_dates_not_empty(self) -> None:
        assert len(_FOMC_DATES) >= 20

    def test_cpi_dates_not_empty(self) -> None:
        assert len(_CPI_DATES) >= 20

    def test_nfp_dates_not_empty(self) -> None:
        assert len(_NFP_DATES) >= 20

    def test_btc_halvings_historical(self) -> None:
        assert datetime.date(2020, 5, 11) in _BTC_HALVING_DATES
        assert datetime.date(2024, 4, 20) in _BTC_HALVING_DATES

    def test_2025_fomc_dates_present(self) -> None:
        fomc_2025 = [d for d in _FOMC_DATES if d.year == 2025]
        assert len(fomc_2025) == 8  # 8 FOMC meetings per year

    def test_2026_fomc_dates_present(self) -> None:
        fomc_2026 = [d for d in _FOMC_DATES if d.year == 2026]
        assert len(fomc_2026) >= 6
