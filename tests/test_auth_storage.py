"""Persistence must wait for a browser acknowledgement, not merely a rerun."""
from dashboard import auth_storage


def test_storage_batches_mutations_without_missing_key_errors(monkeypatch):
    state = {}
    monkeypatch.setattr(auth_storage.st, "session_state", state)
    storage = auth_storage.AuthStorage({})
    storage.setItem("sdl_auth_refresh_token", "test-token", key="component-write")
    operation = state[auth_storage.PENDING_KEY]["operation_id"]
    storage.deleteItem("sdl_auth_persistence_expires_at", key="component-delete")
    assert state[auth_storage.PENDING_KEY]["operation_id"] == operation
    assert state[auth_storage.PENDING_KEY]["changes"] == {
        "sdl_auth_refresh_token": "test-token",
        "sdl_auth_persistence_expires_at": None,
    }


def test_stale_acknowledgement_does_not_discard_pending_write(monkeypatch):
    state = {auth_storage.PENDING_KEY: {"operation_id": "new", "changes": {"key": "value"}}}
    monkeypatch.setattr(auth_storage.st, "session_state", state)
    monkeypatch.setattr(auth_storage, "_bridge", lambda **kwargs: {"ok": True, "operation_id": "old", "values": {}})
    assert auth_storage.browser_auth_storage() is None
    assert auth_storage.PENDING_KEY in state


def test_matching_acknowledgement_completes_pending_write(monkeypatch):
    state = {auth_storage.PENDING_KEY: {"operation_id": "new", "changes": {}}}
    monkeypatch.setattr(auth_storage.st, "session_state", state)
    monkeypatch.setattr(auth_storage, "_bridge", lambda **kwargs: {"ok": True, "operation_id": "new", "values": {"sdl_auth_persistence": "always"}})
    storage = auth_storage.browser_auth_storage()
    assert storage.getItem("sdl_auth_persistence") == "always"
    assert auth_storage.PENDING_KEY not in state
