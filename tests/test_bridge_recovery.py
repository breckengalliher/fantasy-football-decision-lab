from types import SimpleNamespace
import pytest
from dashboard import auth_storage as bridge

QA = SimpleNamespace(url='https://deburhwrnuqeyexpezzo.supabase.co', publishable_key='sb_publishable_test')

class Rerun(Exception):
    pass

def setup(monkeypatch, state=None, clicked=False, result=None):
    state = {} if state is None else state
    events = []
    def button(*args, **kwargs):
        events.append(('button', args[0]))
        return clicked
    def rerun():
        raise Rerun()
    monkeypatch.setenv('RENDER_SERVICE_ID', 'srv-db4ir249v7es7389sshg')
    monkeypatch.setattr(bridge, 'st', SimpleNamespace(session_state=state, button=button,
        caption=lambda text: events.append(('caption', text)),
        warning=lambda text: events.append(('warning', text)), rerun=rerun))
    calls = []
    def component(**kwargs):
        calls.append(kwargs)
        return result
    monkeypatch.setattr(bridge, '_bridge', component)
    return state, events, calls

def test_no_automatic_retry_or_state_loss(monkeypatch):
    original = {'draft': 'pending player', 'command_center_auth_session': 'opaque'}
    state, events, calls = setup(monkeypatch, original.copy())
    assert bridge.browser_auth_storage(QA) is None
    assert state == original
    assert calls[0]['key'] == 'cc_acknowledged_auth_storage_v2'
    assert calls[0]['changes'] == {} and calls[0]['refresh'] is False

def test_clicked_retry_changes_only_component_mount(monkeypatch):
    original = {'draft': 'pending player', 'command_center_auth_session': 'opaque'}
    state, events, calls = setup(monkeypatch, original.copy(), clicked=True)
    with pytest.raises(Rerun):
        bridge.browser_auth_storage(QA)
    assert state == {**original, bridge.RETRY_KEY: 1}
    # Render the replacement; it carries no write, refresh or logout command.
    monkeypatch.setattr(bridge.st, 'button', lambda *a, **kw: False)
    bridge.browser_auth_storage(QA)
    assert calls[-1]['key'].endswith('_retry_1')
    assert calls[-1]['changes'] == {}
    assert not calls[-1]['refresh'] and not calls[-1]['clear']

@pytest.mark.parametrize('pending', [
    {'operation_id': 'save', 'changes': {'sdl_auth_session_v2': 'opaque'}},
    {'operation_id': 'refresh', 'refresh': True},
    {'operation_id': 'logout', 'clear': True},
])
def test_never_remounts_pending_operation(monkeypatch, pending):
    state, events, calls = setup(monkeypatch, {bridge.PENDING_KEY: pending}, clicked=True)
    assert bridge.browser_auth_storage(QA) is None
    assert not any(kind == 'button' for kind, _ in events)
    assert state == {bridge.PENDING_KEY: pending}

def test_retry_limit_preserves_private_state(monkeypatch):
    initial = {bridge.RETRY_KEY: 3, 'draft': 'unchanged'}
    state, events, calls = setup(monkeypatch, initial.copy(), clicked=True)
    assert bridge.browser_auth_storage(QA) is None
    assert state == initial
    assert any(kind == 'warning' for kind, _ in events)
    assert not any(kind == 'button' for kind, _ in events)

@pytest.mark.parametrize('service,url', [('production', QA.url),
    ('srv-db4ir249v7es7389sshg', 'https://different.supabase.co')])
def test_control_requires_both_qa_bindings(monkeypatch, service, url):
    state, events, calls = setup(monkeypatch, clicked=True)
    monkeypatch.setenv('RENDER_SERVICE_ID', service)
    assert bridge.browser_auth_storage(SimpleNamespace(url=url, publishable_key='sb_publishable_test')) is None
    assert not events and not state

def test_acknowledgment_after_retry_returns_storage(monkeypatch):
    state, events, calls = setup(monkeypatch, {bridge.RETRY_KEY: 1},
        result={'ok': True, 'operation_id': '', 'values': {'sdl_auth_persistence': 'always'}})
    storage = bridge.browser_auth_storage(QA)
    assert storage.getItem('sdl_auth_persistence') == 'always'
    assert not events
