"""Macro event calendar for invictus-signals.

Hardcoded 2024-2026 dates for FOMC, CPI, NFP, and Bitcoin halving events.
All functions are pure — no I/O, no side effects.
"""
from __future__ import annotations

import datetime


# ---------------------------------------------------------------------------
# Event database
# ---------------------------------------------------------------------------

# FOMC meeting dates (decision day — when the statement is released)
_FOMC_DATES: frozenset[datetime.date] = frozenset({
    # 2024
    datetime.date(2024, 1, 31),
    datetime.date(2024, 3, 20),
    datetime.date(2024, 5, 1),
    datetime.date(2024, 6, 12),
    datetime.date(2024, 7, 31),
    datetime.date(2024, 9, 18),
    datetime.date(2024, 11, 7),
    datetime.date(2024, 12, 18),
    # 2025
    datetime.date(2025, 1, 29),
    datetime.date(2025, 3, 19),
    datetime.date(2025, 5, 7),
    datetime.date(2025, 6, 18),
    datetime.date(2025, 7, 30),
    datetime.date(2025, 9, 17),
    datetime.date(2025, 11, 5),
    datetime.date(2025, 12, 17),
    # 2026
    datetime.date(2026, 1, 28),
    datetime.date(2026, 3, 18),
    datetime.date(2026, 5, 6),
    datetime.date(2026, 6, 17),
    datetime.date(2026, 7, 29),
    datetime.date(2026, 9, 16),
    datetime.date(2026, 11, 4),
    datetime.date(2026, 12, 16),
})

# CPI release dates (US Bureau of Labor Statistics)
_CPI_DATES: frozenset[datetime.date] = frozenset({
    # 2024
    datetime.date(2024, 1, 11),
    datetime.date(2024, 2, 13),
    datetime.date(2024, 3, 12),
    datetime.date(2024, 4, 10),
    datetime.date(2024, 5, 15),
    datetime.date(2024, 6, 12),
    datetime.date(2024, 7, 11),
    datetime.date(2024, 8, 14),
    datetime.date(2024, 9, 11),
    datetime.date(2024, 10, 10),
    datetime.date(2024, 11, 13),
    datetime.date(2024, 12, 11),
    # 2025
    datetime.date(2025, 1, 15),
    datetime.date(2025, 2, 12),
    datetime.date(2025, 3, 12),
    datetime.date(2025, 4, 10),
    datetime.date(2025, 5, 13),
    datetime.date(2025, 6, 11),
    datetime.date(2025, 7, 15),
    datetime.date(2025, 8, 12),
    datetime.date(2025, 9, 10),
    datetime.date(2025, 10, 14),
    datetime.date(2025, 11, 12),
    datetime.date(2025, 12, 10),
    # 2026
    datetime.date(2026, 1, 14),
    datetime.date(2026, 2, 11),
    datetime.date(2026, 3, 11),
    datetime.date(2026, 4, 9),
    datetime.date(2026, 5, 13),
    datetime.date(2026, 6, 10),
})

# NFP release dates (Bureau of Labor Statistics, first Friday of month)
_NFP_DATES: frozenset[datetime.date] = frozenset({
    # 2024
    datetime.date(2024, 1, 5),
    datetime.date(2024, 2, 2),
    datetime.date(2024, 3, 8),
    datetime.date(2024, 4, 5),
    datetime.date(2024, 5, 3),
    datetime.date(2024, 6, 7),
    datetime.date(2024, 7, 5),
    datetime.date(2024, 8, 2),
    datetime.date(2024, 9, 6),
    datetime.date(2024, 10, 4),
    datetime.date(2024, 11, 1),
    datetime.date(2024, 12, 6),
    # 2025
    datetime.date(2025, 1, 10),
    datetime.date(2025, 2, 7),
    datetime.date(2025, 3, 7),
    datetime.date(2025, 4, 4),
    datetime.date(2025, 5, 2),
    datetime.date(2025, 6, 6),
    datetime.date(2025, 7, 3),
    datetime.date(2025, 8, 1),
    datetime.date(2025, 9, 5),
    datetime.date(2025, 10, 3),
    datetime.date(2025, 11, 7),
    datetime.date(2025, 12, 5),
    # 2026
    datetime.date(2026, 1, 9),
    datetime.date(2026, 2, 6),
    datetime.date(2026, 3, 6),
    datetime.date(2026, 4, 3),
    datetime.date(2026, 5, 1),
    datetime.date(2026, 6, 5),
})

# Bitcoin halving dates (block reward halved approximately every 4 years)
_BTC_HALVING_DATES: frozenset[datetime.date] = frozenset({
    datetime.date(2012, 11, 28),  # First halving: 50→25 BTC
    datetime.date(2016, 7, 9),    # Second halving: 25→12.5 BTC
    datetime.date(2020, 5, 11),   # Third halving: 12.5→6.25 BTC
    datetime.date(2024, 4, 20),   # Fourth halving: 6.25→3.125 BTC
    # Next estimated ~April 2028 (block 1,050,000)
})

# Map event type strings to their date sets
_EVENT_MAP: dict[str, frozenset[datetime.date]] = {
    "fomc": _FOMC_DATES,
    "cpi": _CPI_DATES,
    "nfp": _NFP_DATES,
    "halving": _BTC_HALVING_DATES,
}

_EVENT_DETAILS: dict[str, dict[str, str]] = {
    "fomc": {
        "name": "FOMC Interest Rate Decision",
        "description": "Federal Open Market Committee rate decision. High volatility event.",
        "assets_affected": "SPY, QQQ, all equity + crypto",
    },
    "cpi": {
        "name": "US Consumer Price Index",
        "description": "Monthly inflation data. Market-moving for rate expectations.",
        "assets_affected": "SPY, bonds, USD pairs",
    },
    "nfp": {
        "name": "Non-Farm Payrolls",
        "description": "Monthly jobs report. Released first Friday. High SPY impact.",
        "assets_affected": "SPY, USD pairs",
    },
    "halving": {
        "name": "Bitcoin Halving",
        "description": "Block reward halved. Supply shock event for Bitcoin.",
        "assets_affected": "BTC, ETH, SOL, crypto sector",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_event_day(date: datetime.date, events: str = "all") -> bool:
    """Check if a date is a major macro event day.

    Args:
        date: The date to check.
        events: Comma-separated event types to check, or "all".
                Valid types: "fomc", "cpi", "nfp", "halving".

    Returns:
        True if the date matches any of the specified event types.
    """
    if events == "all":
        check_types = list(_EVENT_MAP.keys())
    else:
        check_types = [e.strip().lower() for e in events.split(",")]

    for event_type in check_types:
        date_set = _EVENT_MAP.get(event_type)
        if date_set is not None and date in date_set:
            return True
    return False


def get_event_info(date: datetime.date) -> dict[str, object] | None:
    """Return event details if the date has a macro event.

    Args:
        date: The date to check.

    Returns:
        Dict with event name, type, description, and assets_affected,
        or None if no event on that date.
    """
    for event_type, date_set in _EVENT_MAP.items():
        if date in date_set:
            details = _EVENT_DETAILS.get(event_type, {})
            return {
                "type": event_type,
                "date": date.isoformat(),
                **details,
            }
    return None


def get_upcoming_events(
    from_date: datetime.date,
    days_ahead: int = 7,
    events: str = "all",
) -> list[dict[str, object]]:
    """Get all macro events in the next N days.

    Args:
        from_date: Starting date (inclusive).
        days_ahead: Number of days to look forward.
        events: Comma-separated event types, or "all".

    Returns:
        List of event dicts sorted by date.
    """
    if events == "all":
        check_types = list(_EVENT_MAP.keys())
    else:
        check_types = [e.strip().lower() for e in events.split(",")]

    results: list[dict[str, object]] = []
    for i in range(days_ahead + 1):
        check_date = from_date + datetime.timedelta(days=i)
        for event_type in check_types:
            date_set = _EVENT_MAP.get(event_type)
            if date_set is not None and check_date in date_set:
                details = _EVENT_DETAILS.get(event_type, {})
                results.append({
                    "type": event_type,
                    "date": check_date.isoformat(),
                    "days_away": i,
                    **details,
                })

    results.sort(key=lambda e: str(e["date"]))
    return results
