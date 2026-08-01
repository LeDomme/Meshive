from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from meshive.services.scan_scheduler import _latest_occurrence


def source(frequency: str, time: str, weekday: int = 0):
    return SimpleNamespace(
        auto_scan_frequency=frequency,
        auto_scan_time=time,
        auto_scan_weekday=weekday,
    )


def test_latest_hourly_occurrence_uses_minute() -> None:
    now = datetime(2026, 7, 31, 12, 15, tzinfo=ZoneInfo("Europe/Berlin"))

    assert _latest_occurrence(source("hourly", "02:10"), now) == datetime(
        2026, 7, 31, 12, 10, tzinfo=ZoneInfo("Europe/Berlin")
    )
    assert _latest_occurrence(source("hourly", "02:20"), now) == datetime(
        2026, 7, 31, 11, 20, tzinfo=ZoneInfo("Europe/Berlin")
    )


def test_latest_daily_and_weekly_occurrences_can_catch_up() -> None:
    now = datetime(2026, 7, 31, 1, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    assert _latest_occurrence(source("daily", "02:00"), now).date().isoformat() == (
        "2026-07-30"
    )
    weekly = _latest_occurrence(source("weekly", "02:00", weekday=0), now)
    assert weekly.isoformat() == "2026-07-27T02:00:00+02:00"
