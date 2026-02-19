"""
US Market hours management.
Determines if market is open and handles pre/post market logic.
"""

from datetime import datetime, time, timezone
import pytz
import structlog

logger = structlog.get_logger()

# US Eastern timezone
ET = pytz.timezone("US/Eastern")

# US Market holidays 2026 (update annually)
US_HOLIDAYS_2026 = [
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Day
    "2026-02-16",  # Presidents' Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
]

# Regular trading hours (ET)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# Extended hours
PRE_MARKET_OPEN = time(4, 0)
AFTER_HOURS_CLOSE = time(20, 0)


def get_et_now() -> datetime:
    """Get current time in US Eastern timezone."""
    return datetime.now(ET)


def is_market_open() -> bool:
    """
    Check if US stock market is currently in regular trading hours.
    Regular hours: Mon-Fri 9:30 AM - 4:00 PM ET
    """
    now_et = get_et_now()

    # Check weekend
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Check holidays
    date_str = now_et.strftime("%Y-%m-%d")
    if date_str in US_HOLIDAYS_2026:
        return False

    # Check time
    current_time = now_et.time()
    return MARKET_OPEN <= current_time < MARKET_CLOSE


def is_extended_hours() -> bool:
    """Check if in pre-market or after-hours."""
    now_et = get_et_now()

    if now_et.weekday() >= 5:
        return False

    date_str = now_et.strftime("%Y-%m-%d")
    if date_str in US_HOLIDAYS_2026:
        return False

    current_time = now_et.time()
    pre_market = PRE_MARKET_OPEN <= current_time < MARKET_OPEN
    after_hours = MARKET_CLOSE <= current_time < AFTER_HOURS_CLOSE
    return pre_market or after_hours


def seconds_until_market_open() -> int:
    """
    Calculate seconds until next market open.
    Returns 0 if market is currently open.
    """
    if is_market_open():
        return 0

    now_et = get_et_now()

    # Find next trading day
    next_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)

    # If past today's open, move to next day
    if now_et.time() >= MARKET_OPEN:
        next_open = next_open.replace(day=next_open.day + 1)

    # Skip weekends
    while next_open.weekday() >= 5:
        next_open = next_open.replace(day=next_open.day + 1)

    # Skip holidays
    while next_open.strftime("%Y-%m-%d") in US_HOLIDAYS_2026:
        next_open = next_open.replace(day=next_open.day + 1)

    diff = (next_open - now_et).total_seconds()
    return max(0, int(diff))


def get_market_status() -> dict:
    """Get detailed market status for display."""
    now_et = get_et_now()

    if is_market_open():
        status = "OPEN"
        emoji = "🟢"
    elif is_extended_hours():
        status = "EXTENDED"
        emoji = "🟡"
    else:
        status = "CLOSED"
        emoji = "🔴"

    secs = seconds_until_market_open()
    hours = secs // 3600
    minutes = (secs % 3600) // 60

    return {
        "status": status,
        "emoji": emoji,
        "current_time_et": now_et.strftime("%H:%M:%S ET"),
        "next_open_in": f"{hours}h {minutes}m" if secs > 0 else "NOW",
        "is_weekend": now_et.weekday() >= 5,
    }
