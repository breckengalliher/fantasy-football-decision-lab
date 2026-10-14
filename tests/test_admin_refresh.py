from datetime import datetime, timedelta, timezone

import pytest

from dashboard import admin_refresh


class Response:
    def __init__(self, payload=None):
        self.payload = payload or {}
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload


def test_authentication_uses_server_secret(monkeypatch):
    monkeypatch.setenv("ADMIN_REFRESH_PASSWORD", "private-pass")
    assert admin_refresh.authenticate("private-pass")
    assert not admin_refresh.authenticate("wrong")


def test_trigger_blocks_duplicate_running_workflow(monkeypatch):
    monkeypatch.setenv("ADMIN_REFRESH_PASSWORD", "x")
    monkeypatch.setenv("GITHUB_ACTIONS_TOKEN", "token")
    monkeypatch.setattr(admin_refresh, "latest_run", lambda workflow, timeout=10: {"status": "in_progress", "created_at": "2026-10-07T10:00:00Z"})
    assert admin_refresh.trigger_refresh("injuries")["state"] == "already_running"


def test_trigger_enforces_cooldown(monkeypatch):
    monkeypatch.setenv("ADMIN_REFRESH_PASSWORD", "x")
    monkeypatch.setenv("GITHUB_ACTIONS_TOKEN", "token")
    created = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    monkeypatch.setattr(admin_refresh, "latest_run", lambda workflow, timeout=10: {"status": "completed", "created_at": created})
    assert admin_refresh.trigger_refresh("context")["state"] == "cooldown"


def test_trigger_dispatches_workflow(monkeypatch):
    monkeypatch.setenv("ADMIN_REFRESH_PASSWORD", "x")
    monkeypatch.setenv("GITHUB_ACTIONS_TOKEN", "token")
    monkeypatch.setattr(admin_refresh, "latest_run", lambda workflow, timeout=10: None)
    calls = []
    monkeypatch.setattr(admin_refresh.requests, "post", lambda url, **kwargs: calls.append((url, kwargs)) or Response())
    result = admin_refresh.trigger_refresh("all")
    assert result["state"] == "requested"
    assert "weekly-production-refresh.yml" in calls[0][0]
    assert calls[0][1]["json"] == {"ref": "main"}


def test_unknown_refresh_is_rejected():
    with pytest.raises(ValueError):
        admin_refresh.trigger_refresh("unknown")
