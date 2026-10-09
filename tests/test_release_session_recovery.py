from dashboard import auth_storage, auth_ui, command_center_v2
from dashboard.supabase_api import SupabaseAPIError
import ast
from pathlib import Path


def test_details_interaction_is_fragment_scoped():
    tree = ast.parse(Path(command_center_v2.__file__).read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_fantasy_details')
    assert any(ast.unparse(node) == 'st.fragment' for node in function.decorator_list)
    assert not any(isinstance(node, ast.Call) and ast.unparse(node.func) == 'st.rerun' for node in ast.walk(function))


def test_details_callback_is_player_scoped(monkeypatch):
    state = {"other-open": True}
    monkeypatch.setattr(command_center_v2.st, "session_state", state)
    command_center_v2._toggle_fantasy_details("selected-open")
    assert state == {"other-open": True, "selected-open": True}
    command_center_v2._toggle_fantasy_details("selected-open")
    assert state["selected-open"] is False


def test_temporary_restore_failure_preserves_credentials(monkeypatch):
    state = {}
    monkeypatch.setattr(auth_ui.st, "session_state", state)
    monkeypatch.setattr(auth_ui.st, "rerun", lambda: None)
    monkeypatch.setattr(auth_ui.st, "warning", lambda *args: None)
    monkeypatch.setattr(auth_ui.st, "button", lambda *args, **kwargs: False)
    storage = auth_storage.AuthStorage({auth_ui.STORAGE_KEY: "test-token"})
    class API:
        calls = 0
        def refresh(self, token):
            self.calls += 1
            raise SupabaseAPIError("Temporary outage", retryable=True)
    api = API()
    assert auth_ui.restore_session(api, storage) is None
    assert storage.getItem(auth_ui.STORAGE_KEY) == "test-token"
    assert auth_storage.PENDING_KEY not in state
    assert auth_ui.restore_session(api, storage) is None
    assert api.calls == 1
    monkeypatch.setattr(auth_ui.st, "button", lambda *args, **kwargs: True)
    auth_ui.restore_session(api, storage)
    assert api.calls == 2


def test_rejected_restore_credentials_are_removed(monkeypatch):
    monkeypatch.setattr(auth_ui.st, "session_state", {})
    storage = auth_storage.AuthStorage({auth_ui.STORAGE_KEY: "revoked-test-token"})
    class API:
        def refresh(self, token):
            raise SupabaseAPIError("Rejected credential")
    assert auth_ui.restore_session(API(), storage) is None
    assert storage.getItem(auth_ui.STORAGE_KEY) is None
