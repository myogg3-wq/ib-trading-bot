"""
US Market hours management.
Determines if market is open and handles pre/post market logic.
"""

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Optional
from dateutil.easter import easter
import pytz
import structlog

from app.config import settings

logger = structlog.get_logger()

# US Eastern timezone
ET = pytz.timezone("US/Eastern")
KST = pytz.timezone("Asia/Seoul")
HKT = pytz.timezone("Asia/Hong_Kong")
CST = pytz.timezone("Asia/Shanghai")
JST = pytz.timezone("Asia/Tokyo")

# Regular trading hours (ET)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

# Extended hours
PRE_MARKET_OPEN = time(4, 0)
AFTER_HOURS_CLOSE = time(20, 0)

# Korea Exchange regular trading hours (KST).
# Holiday handling is intentionally conservative here: weekends are excluded,
# exchange holidays are still rejected safely by KIS if a special closure occurs.
KRX_MARKET_OPEN = time(9, 0)
KRX_MARKET_CLOSE = time(15, 30)

ASIA_MARKET_SESSIONS = {
    "HKEX": (HKT, [(time(9, 30), time(12, 0)), (time(13, 0), time(16, 0))]),
    "SSE": (CST, [(time(9, 30), time(11, 30)), (time(13, 0), time(15, 0))]),
    "SZSE": (CST, [(time(9, 30), time(11, 30)), (time(13, 0), time(15, 0))]),
    "TSE": (JST, [(time(9, 0), time(11, 30)), (time(12, 30), time(15, 30))]),
}


def _configured_market_holidays(market: str) -> set[str]:
    """Return operator-configured exchange holidays as ISO date strings."""
    key = str(market or "").strip().lower()
    raw = str(getattr(settings, f"market_holidays_{key}", "") or "")
    holidays: set[str] = set()
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        try:
            holidays.add(date.fromisoformat(text).isoformat())
        except ValueError:
            logger.warning("Ignoring invalid market holiday date", market=market, value=text)
    return holidays


def _is_configured_market_holiday(market: str, day: date) -> bool:
    return day.isoformat() in _configured_market_holidays(market)


def _observed(day: date) -> date:
    """Return market holiday observed date when fixed-date holiday lands on weekend."""
    if day.weekday() == 5:  # Saturday -> Friday
        return day - timedelta(days=1)
    if day.weekday() == 6:  # Sunday -> Monday
        return day + timedelta(days=1)
    return day


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Get nth weekday in a month (weekday: Monday=0 ... Sunday=6)."""
    first = date(year, month, 1)
    delta = (weekday - first.weekday()) % 7
    return first + timedelta(days=delta + 7 * (n - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Get last weekday in a month (weekday: Monday=0 ... Sunday=6)."""
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)

    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


@lru_cache(maxsize=16)
def get_us_market_holidays(year: int) -> set[str]:
    """
    Compute major NYSE market holidays for a given year.
    This avoids hardcoding a single year and prevents stale holiday logic.
    """
    holidays = {
        _observed(date(year, 1, 1)),                     # New Year's Day
        _nth_weekday_of_month(year, 1, 0, 3),           # Martin Luther King Jr. Day
        _nth_weekday_of_month(year, 2, 0, 3),           # Presidents' Day
        easter(year) - timedelta(days=2),               # Good Friday
        _last_weekday_of_month(year, 5, 0),             # Memorial Day
        _observed(date(year, 6, 19)),                   # Juneteenth
        _observed(date(year, 7, 4)),                    # Independence Day
        _nth_weekday_of_month(year, 9, 0, 1),           # Labor Day
        _nth_weekday_of_month(year, 11, 3, 4),          # Thanksgiving
        _observed(date(year, 12, 25)),                  # Christmas
    }
    return {d.isoformat() for d in holidays}


def _is_trading_day(day: date) -> bool:
    """Check if the date is a regular US market trading day."""
    if day.weekday() >= 5:
        return False
    if day.isoformat() in get_us_market_holidays(day.year):
        return False
    return not _is_configured_market_holiday("US", day)


def _is_market_open_at(now_et: datetime) -> bool:
    """Time-aware market open check for a given ET datetime."""
    if not _is_trading_day(now_et.date()):
        return False
    current_time = now_et.time()
    return MARKET_OPEN <= current_time < MARKET_CLOSE


def _is_krx_trading_day(day: date) -> bool:
    """Check KRX trading day with operator-maintained special holidays."""
    return day.weekday() < 5 and not _is_configured_market_holiday("KRX", day)


def _is_krx_market_open_at(now_kst: datetime) -> bool:
    """Time-aware KRX regular session check for a KST datetime."""
    if not _is_krx_trading_day(now_kst.date()):
        return False
    current_time = now_kst.time()
    return KRX_MARKET_OPEN <= current_time < KRX_MARKET_CLOSE


def _is_basic_weekday(day: date, market: Optional[str] = None) -> bool:
    """Trading day check for Asia markets with optional holiday overrides."""
    if day.weekday() >= 5:
        return False
    if market and _is_configured_market_holiday(market, day):
        return False
    return True


def _is_session_open_at(now_local: datetime, sessions: list[tuple[time, time]], market: Optional[str] = None) -> bool:
    if not _is_basic_weekday(now_local.date(), market):
        return False
    current_time = now_local.time()
    return any(start <= current_time < end for start, end in sessions)


def _is_extended_hours_at(now_et: datetime) -> bool:
    """Time-aware extended-hours check for a given ET datetime."""
    if not _is_trading_day(now_et.date()):
        return False
    current_time = now_et.time()
    pre_market = PRE_MARKET_OPEN <= current_time < MARKET_OPEN
    after_hours = MARKET_CLOSE <= current_time < AFTER_HOURS_CLOSE
    return pre_market or after_hours


def get_et_now() -> datetime:
    """Get current time in US Eastern timezone."""
    return datetime.now(ET)


def get_kst_now() -> datetime:
    """Get current time in Korea Standard Time."""
    return datetime.now(KST)


def _market_key_for_ticker(ticker: str) -> str:
    from app.gateway.symbol_mapper import is_kis_domestic_symbol, split_tv_ticker

    if is_kis_domestic_symbol(ticker):
        return "KRX"
    exchange, _ = split_tv_ticker(ticker)
    if exchange in ASIA_MARKET_SESSIONS:
        return exchange
    return "US"


def get_et_day_bounds_utc(now_utc: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    Return current ET calendar day boundaries converted to UTC.
    Used for "today" metrics so daily risk/report windows match US market timezone.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)
    start_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
    end_et = start_et + timedelta(days=1)
    return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)


def get_kst_day_bounds_utc(now_utc: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    Return current KST calendar day boundaries converted to UTC.
    Used for domestic/KRX daily duplicate-buy checks.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(KST)
    start_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    end_kst = start_kst + timedelta(days=1)
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)


def get_et_week_bounds_utc(now_utc: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Return current ET week boundaries (Mon 00:00 to next Mon 00:00) in UTC."""
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)
    week_start_et = (now_et - timedelta(days=now_et.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    week_end_et = week_start_et + timedelta(days=7)
    return week_start_et.astimezone(timezone.utc), week_end_et.astimezone(timezone.utc)


def is_market_open() -> bool:
    """
    Check if US stock market is currently in regular trading hours.
    Regular hours: Mon-Fri 9:30 AM - 4:00 PM ET
    """
    return _is_market_open_at(get_et_now())


def is_krx_market_open() -> bool:
    """Check if KRX is currently in regular trading hours."""
    return _is_krx_market_open_at(get_kst_now())


def is_asia_market_open(market: str) -> bool:
    """Check if a supported Asia market is currently in regular trading hours."""
    market_key = str(market or "").strip().upper()
    rule = ASIA_MARKET_SESSIONS.get(market_key)
    if not rule:
        return False
    tz, sessions = rule
    return _is_session_open_at(datetime.now(tz), sessions, market_key)


def is_market_open_for_ticker(ticker: str) -> bool:
    """Route market-hours checks by symbol market."""
    market_key = _market_key_for_ticker(ticker)
    if market_key == "KRX":
        return is_krx_market_open()
    if market_key in ASIA_MARKET_SESSIONS:
        return is_asia_market_open(market_key)
    return is_market_open()


def is_any_supported_market_open() -> bool:
    """Return True when any supported regular session is open."""
    return (
        is_market_open()
        or is_krx_market_open()
        or any(is_asia_market_open(market) for market in ASIA_MARKET_SESSIONS)
    )


def is_extended_hours() -> bool:
    """Check if in pre-market or after-hours."""
    return _is_extended_hours_at(get_et_now())


def seconds_until_market_open() -> int:
    """
    Calculate seconds until next market open.
    Returns 0 if market is currently open.
    """
    now_et = get_et_now()
    if _is_market_open_at(now_et):
        return 0

    if _is_trading_day(now_et.date()) and now_et.time() < MARKET_OPEN:
        next_open_date = now_et.date()
    else:
        next_open_date = now_et.date() + timedelta(days=1)
        while not _is_trading_day(next_open_date):
            next_open_date += timedelta(days=1)

    naive_open = datetime.combine(next_open_date, MARKET_OPEN)
    next_open = ET.localize(naive_open)
    diff = (next_open - now_et).total_seconds()
    return max(0, int(diff))


def seconds_until_krx_market_open() -> int:
    """Calculate seconds until next KRX regular open."""
    now_kst = get_kst_now()
    if _is_krx_market_open_at(now_kst):
        return 0

    if _is_krx_trading_day(now_kst.date()) and now_kst.time() < KRX_MARKET_OPEN:
        next_open_date = now_kst.date()
    else:
        next_open_date = now_kst.date() + timedelta(days=1)
        while not _is_krx_trading_day(next_open_date):
            next_open_date += timedelta(days=1)

    naive_open = datetime.combine(next_open_date, KRX_MARKET_OPEN)
    next_open = KST.localize(naive_open)
    diff = (next_open - now_kst).total_seconds()
    return max(0, int(diff))


def seconds_until_asia_market_open(market: str) -> int:
    """Calculate seconds until next regular session for a supported Asia market."""
    market_key = str(market or "").strip().upper()
    rule = ASIA_MARKET_SESSIONS.get(market_key)
    if not rule:
        return seconds_until_market_open()

    tz, sessions = rule
    now_local = datetime.now(tz)
    if _is_session_open_at(now_local, sessions, market_key):
        return 0

    cursor_date = now_local.date()
    for _ in range(10):
        if _is_basic_weekday(cursor_date, market_key):
            for session_open, _ in sessions:
                if cursor_date > now_local.date() or now_local.time() < session_open:
                    next_open = tz.localize(datetime.combine(cursor_date, session_open))
                    return max(0, int((next_open - now_local).total_seconds()))
        cursor_date += timedelta(days=1)

    return 0


def get_market_status() -> dict:
    """Get detailed market status for display."""
    now_et = get_et_now()

    if _is_market_open_at(now_et):
        status = "OPEN"
        emoji = "🟢"
    elif _is_extended_hours_at(now_et):
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


def get_krx_market_status() -> dict:
    """Get detailed KRX market status for display."""
    now_kst = get_kst_now()

    if _is_krx_market_open_at(now_kst):
        status = "OPEN"
        emoji = "🟢"
    else:
        status = "CLOSED"
        emoji = "🔴"

    secs = seconds_until_krx_market_open()
    hours = secs // 3600
    minutes = (secs % 3600) // 60

    return {
        "status": status,
        "emoji": emoji,
        "current_time_kst": now_kst.strftime("%H:%M:%S KST"),
        "next_open_in": f"{hours}h {minutes}m" if secs > 0 else "NOW",
        "is_weekend": now_kst.weekday() >= 5,
    }


def get_asia_market_status(market: str) -> dict:
    """Get detailed status for a supported Asia market."""
    market_key = str(market or "").strip().upper()
    rule = ASIA_MARKET_SESSIONS.get(market_key)
    if not rule:
        return get_market_status()
    tz, sessions = rule
    now_local = datetime.now(tz)

    if _is_session_open_at(now_local, sessions, market_key):
        status = "OPEN"
        emoji = "🟢"
    else:
        status = "CLOSED"
        emoji = "🔴"

    secs = seconds_until_asia_market_open(market_key)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    tz_label = {
        "HKEX": "HKT",
        "SSE": "CST",
        "SZSE": "CST",
        "TSE": "JST",
    }.get(market_key, "LOCAL")

    return {
        "status": status,
        "emoji": emoji,
        "market": market_key,
        "current_time_local": now_local.strftime(f"%H:%M:%S {tz_label}"),
        "next_open_in": f"{hours}h {minutes}m" if secs > 0 else "NOW",
        "is_weekend": now_local.weekday() >= 5,
    }


def get_market_status_for_ticker(ticker: str) -> dict:
    """Route market status by symbol market."""
    market_key = _market_key_for_ticker(ticker)
    if market_key == "KRX":
        return get_krx_market_status()
    if market_key in ASIA_MARKET_SESSIONS:
        return get_asia_market_status(market_key)
    return get_market_status()
