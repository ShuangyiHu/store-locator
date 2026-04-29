"""Operating-hours parsing and is_open_now check.

CSV format: "HH:MM-HH:MM" or the literal "closed" (lowercase).
The dataset uses "24:00" to mean end-of-day, which `time.fromisoformat`
rejects — handled explicitly below.
"""

from __future__ import annotations

from datetime import datetime, time

# weekday() index → CSV column suffix
_DAY_KEYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# "24:00" → end-of-day sentinel. We can't use time(24, 0) (out of range), so
# pick the largest representable time on the clock.
_END_OF_DAY = time(23, 59, 59, 999_999)


def _parse_clock(value: str) -> time:
    if value == "24:00":
        return _END_OF_DAY
    return time.fromisoformat(value)


def parse_hours(value: str) -> tuple[time, time] | None:
    """Parse one day's hours. Returns None for `closed`. Raises ValueError on malformed input."""
    if value is None:
        raise ValueError("hours value is None")
    v = value.strip()
    if v.lower() == "closed":
        return None

    parts = v.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid hours format: {value!r}")

    open_t = _parse_clock(parts[0].strip())
    close_t = _parse_clock(parts[1].strip())
    if open_t >= close_t:
        raise ValueError(f"open_time must be < close_time: {value!r}")
    return (open_t, close_t)


def is_open_now(store_hours: dict[str, str], now: datetime | None = None) -> bool:
    """Return True if `now` falls within the store's hours for that weekday.

    Time-zone simplification: store hours are interpreted as wall-clock time
    in whatever zone `now` represents. Defaults to server local time.
    """
    if now is None:
        now = datetime.now()

    day_key = _DAY_KEYS[now.weekday()]
    raw = store_hours.get(day_key)
    if not raw:
        return False

    try:
        parsed = parse_hours(raw)
    except ValueError:
        return False

    if parsed is None:  # closed
        return False

    open_t, close_t = parsed
    current = now.time()
    return open_t <= current < close_t


def store_hours_dict(store) -> dict[str, str]:
    """Build {'mon': '08:00-22:00', ...} from a Store ORM instance."""
    return {key: getattr(store, f"hours_{key}") for key in _DAY_KEYS}
