"""US equity regular session helpers in America/New_York timezone.

Used by intraday VWAP-style strategies so bar timestamps stay aligned with NYSE clocks.
"""

from __future__ import annotations

from datetime import UTC, datetime, time as dt_time, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")


def utc_from_unix_ms(epoch_ms: int) -> datetime:
    return datetime.fromtimestamp(epoch_ms / 1000.0, tz=UTC)


def ny_from_unix_ms(epoch_ms: int) -> datetime:
    return utc_from_unix_ms(epoch_ms).astimezone(NY_TZ)


def ny_session_bounds_for_date(ny_date: datetime.date) -> tuple[datetime, datetime]:
    """Regular session anchors (09:30–16:00 America/New_York)."""
    open_dt = datetime.combine(ny_date, dt_time(9, 30), tzinfo=NY_TZ)
    close_dt = datetime.combine(ny_date, dt_time(16, 0), tzinfo=NY_TZ)
    return open_dt, close_dt


def is_weekday_et(ny_dt: datetime) -> bool:
    return ny_dt.weekday() < 5


def ny_bar_end(ny_bar_start: datetime, timeframe_minutes: int) -> datetime:
    return ny_bar_start + timedelta(minutes=timeframe_minutes)


def bar_end_in_trade_window(
    unix_ms_bar_start: int,
    timeframe_minutes: int,
    open_plus_minutes: int = 3,
    close_minus_minutes: int = 27,
) -> bool:
    """True if regular-session bar **ends** inside the discretionary trade window."""

    utc_start = utc_from_unix_ms(unix_ms_bar_start)
    utc_end = utc_start + timedelta(minutes=timeframe_minutes)

    ny_end = utc_end.astimezone(NY_TZ)

    if not is_weekday_et(ny_end):
        return False

    open_plain, close_plain = ny_session_bounds_for_date(ny_end.date())

    window_open = open_plain + timedelta(minutes=open_plus_minutes)
    window_close = close_plain - timedelta(minutes=close_minus_minutes)

    return window_open <= ny_end <= window_close


def bar_end_in_regular_session(unix_ms_bar_start: int, timeframe_minutes: int) -> bool:
    utc_start = utc_from_unix_ms(unix_ms_bar_start)
    utc_end = utc_start + timedelta(minutes=timeframe_minutes)

    ny_end = utc_end.astimezone(NY_TZ)

    if not is_weekday_et(ny_end):
        return False

    open_plain, close_plain = ny_session_bounds_for_date(ny_end.date())
    return open_plain <= ny_end <= close_plain


def bar_start_in_regular_session(unix_ms_bar_start: int) -> bool:
    """TradingView `time`-style tekshiruv: bar ochilish payti ET da 09:30–16:00 oralig‘ida."""

    ny_start = utc_from_unix_ms(unix_ms_bar_start).astimezone(NY_TZ)

    if not is_weekday_et(ny_start):
        return False

    open_plain, close_plain = ny_session_bounds_for_date(ny_start.date())
    return open_plain <= ny_start < close_plain


def ny_session_trade_bounds_for_date(
    ny_date: datetime.date,
    open_plus_minutes: int,
    close_minus_minutes: int,
) -> tuple[datetime, datetime]:
    """(window_open_dt, exclusive_end_dt) — Pine: barTime ∈ [start, end)."""

    open_plain, close_plain = ny_session_bounds_for_date(ny_date)
    window_open = open_plain + timedelta(minutes=open_plus_minutes)
    exclusive_end = close_plain - timedelta(minutes=close_minus_minutes)
    return window_open, exclusive_end


def bar_start_in_trade_window(
    unix_ms_bar_start: int,
    open_plus_minutes: int = 3,
    close_minus_minutes: int = 27,
) -> bool:
    """Pine `inTime`: bar ochilish `time` bilan [startDelay, close−before)."""

    ny_start = utc_from_unix_ms(unix_ms_bar_start).astimezone(NY_TZ)

    if not is_weekday_et(ny_start):
        return False

    window_open, exclusive_end = ny_session_trade_bounds_for_date(ny_start.date(), open_plus_minutes, close_minus_minutes)

    return window_open <= ny_start < exclusive_end


def group_unix_ms_bar_starts_by_ny_trade_date(epoch_ms_series: Iterable[int]) -> dict[datetime.date, list[int]]:
    """Group bar start timestamps (ms) using the ET calendar date seen at midnight proxy.

    Practical rule: classify by converting start instant to ET date.
    """

    buckets: dict[datetime.date, list[int]] = {}
    for ms in epoch_ms_series:
        ny_start = utc_from_unix_ms(ms).astimezone(NY_TZ)
        day = ny_start.date()
        buckets.setdefault(day, []).append(ms)

    for day_ms in buckets.values():
        day_ms.sort()
    return buckets
