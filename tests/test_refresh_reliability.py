from datetime import datetime, timedelta, timezone
import pytest
import requests
from dashboard.providers import http_retry
from dashboard.refresh_health import expected_slots, job_health, matured_slot


NOW = datetime(2026, 10, 9, 15, tzinfo=timezone.utc)


def test_new_schedule_slot_does_not_mask_overdue_earlier_slot():
    slots = [NOW - timedelta(hours=3), NOW - timedelta(minutes=10)]
    assert not job_health([], slots[-1].isoformat(), NOW)["overdue"]
    assert job_health([], matured_slot(slots, NOW), NOW)["overdue"]
    assert matured_slot([slots[-1]], NOW) is None


def test_timeout_retries_have_bounded_exponential_backoff(monkeypatch):
    calls, delays = [], []
    def get(*args, **kwargs):
        calls.append(kwargs["timeout"])
        raise requests.Timeout("timeout")
    monkeypatch.setattr(http_retry.requests, "get", get)
    monkeypatch.setattr(http_retry.time, "sleep", delays.append)
    with pytest.raises(requests.Timeout):
        http_retry.get_with_retry("https://example.test", timeout=2)
    assert calls == [2, 2, 2]
    assert delays == [.5, 1.]


def test_nontransient_provider_error_is_not_retried(monkeypatch):
    calls = []
    response = requests.Response()
    response.status_code = 403
    def get(*args, **kwargs):
        calls.append(1)
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(http_retry.requests, "get", get)
    with pytest.raises(requests.HTTPError):
        http_retry.get_with_retry("https://example.test")
    assert len(calls) == 1


def test_missing_schedule_and_failed_jobs_are_not_success():
    result = job_health([], (NOW-timedelta(hours=3)).isoformat(), NOW)
    assert result["overdue"] and result["last_result"] == "unverified"
    run = {"created_at": NOW.isoformat(), "event": "schedule", "status": "completed", "conclusion": "failure"}
    result = job_health([run], NOW.isoformat(), NOW)
    assert not result["overdue"]
    assert result["consecutive_failures"] == 1
    assert result["last_successful_completion"] is None


def test_successful_noop_never_claims_verified_publication():
    run = {"created_at": NOW.isoformat(), "event": "schedule", "status": "completed", "conclusion": "success", "updated_at": NOW.isoformat()}
    result = job_health([run], NOW.isoformat(), NOW)
    assert not result["overdue"]
    assert result["last_successful_completion"] == NOW.isoformat()
    assert not result["publication_verified"]


def test_schedule_is_central_time_and_independent_of_traffic():
    workflow = 'on:\n  schedule:\n    - cron: "0 6,17 * * *"\n      timezone: "America/Chicago"'
    slots = expected_slots(workflow, datetime(2026, 10, 9, tzinfo=timezone.utc),
                           datetime(2026, 10, 10, tzinfo=timezone.utc))
    assert [slot.hour for slot in slots] == [11, 22]
