from datetime import datetime, timedelta, timezone

from dashboard.auth_ui import _delete_if_present, persistence_expired


NOW = datetime(2026, 10, 8, 18, tzinfo=timezone.utc)


def test_remember_me_expires_at_stored_deadline():
    assert not persistence_expired("remember", (NOW + timedelta(days=1)).isoformat(), NOW)
    assert persistence_expired("remember", (NOW - timedelta(seconds=1)).isoformat(), NOW)


def test_missing_or_invalid_remember_deadline_is_not_trusted():
    assert persistence_expired("remember", None, NOW)
    assert persistence_expired("remember", "not-a-date", NOW)


def test_always_and_session_modes_do_not_use_remember_deadline():
    assert not persistence_expired("always", None, NOW)
    assert not persistence_expired("session", None, NOW)


def test_missing_local_storage_key_can_be_cleared_safely():
    class EmptyStorage:
        def deleteItem(self, item_key, key):
            raise KeyError(item_key)

    _delete_if_present(EmptyStorage(), "missing", component_key="test_clear")
