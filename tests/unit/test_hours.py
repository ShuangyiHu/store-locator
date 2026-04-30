from datetime import datetime, time

import pytest

from app.utils.hours import is_open_now, parse_hours


class TestParseHours:
    def test_valid_range(self):
        assert parse_hours("08:00-22:00") == (time(8, 0), time(22, 0))

    def test_closed(self):
        assert parse_hours("closed") is None

    def test_closed_uppercase_tolerated(self):
        assert parse_hours("CLOSED") is None

    def test_24_00_treated_as_end_of_day(self):
        open_t, close_t = parse_hours("07:00-24:00")
        assert open_t == time(7, 0)
        # End-of-day sentinel: must compare > any normal close time
        assert close_t > time(23, 59)

    def test_missing_dash_raises(self):
        with pytest.raises(ValueError):
            parse_hours("8 to 22")

    def test_open_after_close_raises(self):
        with pytest.raises(ValueError):
            parse_hours("22:00-08:00")

    def test_invalid_clock_raises(self):
        with pytest.raises(ValueError):
            parse_hours("9999-22:00")


class TestIsOpenNow:
    HOURS_WEEKDAY_DAY = {
        "mon": "08:00-22:00",
        "tue": "08:00-22:00",
        "wed": "08:00-22:00",
        "thu": "08:00-22:00",
        "fri": "08:00-22:00",
        "sat": "closed",
        "sun": "10:00-20:00",
    }

    def test_within_hours_returns_true(self):
        # Monday 2026-04-27 12:00
        assert is_open_now(self.HOURS_WEEKDAY_DAY, datetime(2026, 4, 27, 12, 0)) is True

    def test_before_open_returns_false(self):
        assert is_open_now(self.HOURS_WEEKDAY_DAY, datetime(2026, 4, 27, 7, 30)) is False

    def test_after_close_returns_false(self):
        assert is_open_now(self.HOURS_WEEKDAY_DAY, datetime(2026, 4, 27, 22, 30)) is False

    def test_closed_day_returns_false(self):
        # Saturday — explicit "closed"
        assert is_open_now(self.HOURS_WEEKDAY_DAY, datetime(2026, 5, 2, 12, 0)) is False

    def test_24_00_close_includes_late_evening(self):
        hours = {**self.HOURS_WEEKDAY_DAY, "wed": "08:00-24:00"}
        # Wednesday 23:30 — should be open thanks to 24:00 sentinel
        assert is_open_now(hours, datetime(2026, 4, 29, 23, 30)) is True

    def test_invalid_hours_safely_returns_false(self):
        # Defensive: malformed hours should not raise from is_open_now
        assert is_open_now({**self.HOURS_WEEKDAY_DAY, "mon": "garbage"},
                           datetime(2026, 4, 27, 12, 0)) is False
