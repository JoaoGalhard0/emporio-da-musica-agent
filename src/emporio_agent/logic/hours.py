from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

# weekday(): Monday=0 ... Sunday=6. Manual section 2.
OPENING_HOURS = {
    **{d: (time(9, 0), time(18, 0)) for d in range(0, 5)},
    5: (time(9, 0), time(13, 0)),
}


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm; needed only for Good Friday."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def national_holidays(year: int) -> set[date]:
    """Nationwide holidays only. State and municipal ones (e.g. Campo Grande's anniversary on
    August 26) are not in the provided material and are a known limitation."""
    fixed = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]
    return {date(year, m, d) for m, d in fixed} | {_easter(year) - timedelta(days=2)}


def _is_open_day(day: date) -> bool:
    return day.weekday() in OPENING_HOURS and day not in national_holidays(day.year)


@dataclass(frozen=True)
class StoreStatus:
    is_open: bool
    now: datetime
    today_hours: str | None  # None when closed all day
    next_open: datetime | None  # None when open right now
    is_holiday: bool


def store_status(now: datetime) -> StoreStatus:
    day = now.date()
    holiday = day in national_holidays(day.year)
    hours = OPENING_HOURS.get(day.weekday())
    open_today = hours is not None and not holiday
    today_hours = f"{hours[0]:%H:%M} às {hours[1]:%H:%M}" if open_today else None

    if open_today and hours[0] <= now.time() < hours[1]:
        return StoreStatus(True, now, today_hours, None, holiday)

    # Closed now: find the next opening, either later today or on the next open day.
    candidate = day
    if open_today and now.time() < hours[0]:
        return StoreStatus(False, now, today_hours, datetime.combine(day, hours[0], now.tzinfo), holiday)
    while True:
        candidate += timedelta(days=1)
        if _is_open_day(candidate):
            opens = OPENING_HOURS[candidate.weekday()][0]
            return StoreStatus(False, now, today_hours, datetime.combine(candidate, opens, now.tzinfo), holiday)
