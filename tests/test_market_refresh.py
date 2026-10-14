from datetime import datetime, timedelta, timezone

from src.refresh_market_snapshot import refresh_due, target_interval


def central_time(year, month, day, hour):
    from zoneinfo import ZoneInfo
    return datetime(year, month, day, hour, tzinfo=ZoneInfo("America/Chicago"))


def test_adaptive_market_cadence_prioritizes_lineup_windows():
    assert target_interval(central_time(2026, 10, 7, 12)) == timedelta(hours=6)  # Wednesday
    assert target_interval(central_time(2026, 10, 8, 12)) == timedelta(hours=2)  # Thursday
    assert target_interval(central_time(2026, 10, 10, 12)) == timedelta(hours=1)  # Saturday
    assert target_interval(central_time(2026, 10, 11, 12)) == timedelta(minutes=30)  # Sunday


def test_refresh_due_respects_current_window():
    now = central_time(2026, 10, 11, 12)
    assert not refresh_due((now.astimezone(timezone.utc) - timedelta(minutes=20)).isoformat(), now)
    assert refresh_due((now.astimezone(timezone.utc) - timedelta(minutes=31)).isoformat(), now)
