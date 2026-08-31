from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from meshive.services import scan_scheduler
from meshive.services.scan_scheduler import _is_due, _latest_occurrence


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


def test_scheduler_logs_evaluation_failure_and_keeps_looping(monkeypatch) -> None:
    logged_messages = []
    waits = iter([False, True])
    monkeypatch.setattr(scan_scheduler._stop, "wait", lambda _seconds: next(waits))
    monkeypatch.setattr(
        scan_scheduler,
        "_start_due_scans",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        scan_scheduler.logger,
        "exception",
        lambda message: logged_messages.append(message),
    )

    scan_scheduler._loop()

    assert logged_messages == ["Scheduled scan evaluation failed"]


def test_invalid_timezone_warning_is_deduplicated(monkeypatch) -> None:
    logged_messages = []
    scan_scheduler._reported_invalid_timezones.clear()
    monkeypatch.setattr(
        scan_scheduler.logger,
        "warning",
        lambda message, *args: logged_messages.append(message % args),
    )
    invalid_source = SimpleNamespace(
        id=42,
        name="Broken schedule",
        auto_scan_timezone="Not/A-Timezone",
    )

    assert _is_due(None, invalid_source) is False
    assert _is_due(None, invalid_source) is False

    assert logged_messages == [
        "Skipping scheduled scan for source 42 (Broken schedule): unknown timezone 'Not/A-Timezone'"
    ]
