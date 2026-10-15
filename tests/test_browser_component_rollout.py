from types import SimpleNamespace
import pytest
from dashboard.browser_components import native_enabled
from dashboard import auth_storage, onboarding_storage
from test_bridge_recovery import setup


@pytest.mark.parametrize('mode,expected', [('auto', False), ('native', True), ('legacy', False)])
def test_explicit_server_rollout_without_qa_bindings(mode, expected):
    api = SimpleNamespace(url='https://production-example.supabase.co')
    assert native_enabled(api, {'RENDER_SERVICE_ID': 'production-example',
                               'SDL_BROWSER_COMPONENT_TRANSPORT': mode}) is expected


def test_empty_api_never_enables_native():
    assert not native_enabled(None, {'SDL_BROWSER_COMPONENT_TRANSPORT': 'native'})


def test_invalid_server_rollout_fails_visibly():
    with pytest.raises(ValueError, match='SDL_BROWSER_COMPONENT_TRANSPORT'):
        native_enabled(None, {'SDL_BROWSER_COMPONENT_TRANSPORT': 'typo'})


def test_explicit_native_uses_same_auth_and_guide_path(monkeypatch):
    pending = {'operation_id': 'original', 'changes': {'sdl_auth_persistence': 'remember'}}
    state, events, legacy = setup(monkeypatch, {auth_storage.PENDING_KEY: pending, 'draft': 'preserve'})
    monkeypatch.setenv('RENDER_SERVICE_ID', 'non-qa-test-service')
    monkeypatch.setenv('SDL_BROWSER_COMPONENT_TRANSPORT', 'native')
    api = SimpleNamespace(url='https://production-example.supabase.co', publishable_key='test-public')
    seen = []
    monkeypatch.setattr(auth_storage, '_native_bridge', lambda **kw: seen.append(kw))
    assert auth_storage.browser_auth_storage(api) is None
    assert onboarding_storage.enabled(api)
    assert not legacy and seen[0]['operation_id'] == 'original'
    assert seen[0]['auth_url'] == api.url and seen[0]['publishable_key'] == api.publishable_key
    assert not seen[0]['refresh'] and not seen[0]['clear']
    assert state['draft'] == 'preserve' and state[auth_storage.PENDING_KEY] == pending
