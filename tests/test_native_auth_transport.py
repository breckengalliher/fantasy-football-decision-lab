from types import SimpleNamespace
from dashboard import auth_storage as bridge
from test_bridge_recovery import setup, QA


def test_native_transport_reuses_exact_pending_operation(monkeypatch):
    pending = {'operation_id': 'existing', 'changes': {'sdl_auth_persistence': 'remember'}}
    state, events, calls = setup(monkeypatch, {bridge.PENDING_KEY: pending, 'draft': 'keep'})
    bridge.st.query_params['qa_auth_transport'] = 'native'
    native = []
    monkeypatch.setattr(bridge, '_native_bridge', lambda **kwargs: native.append(kwargs))
    assert bridge.browser_auth_storage(QA) is None
    assert not calls and native[0]['operation_id'] == 'existing'
    assert native[0]['changes'] == pending['changes']
    assert not native[0]['refresh'] and not native[0]['clear']
    assert state['draft'] == 'keep' and state[bridge.PENDING_KEY] == pending


def test_native_experiment_cannot_enable_on_production(monkeypatch):
    state, events, calls = setup(monkeypatch)
    bridge.st.query_params['qa_auth_transport'] = 'native'
    monkeypatch.setenv('RENDER_SERVICE_ID', 'production')
    monkeypatch.setattr(bridge, '_native_bridge', lambda **kwargs: (_ for _ in ()).throw(AssertionError('native on production')))
    bridge.browser_auth_storage(QA)
    assert len(calls) == 1


def test_native_adapter_passes_values_as_data_not_source(monkeypatch):
    observed = {}
    def mount(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(ack={'ok': True})
    monkeypatch.setattr(bridge, '_native_component', lambda: mount)
    assert bridge._native_bridge(key='fixed', default=None, changes={'text':'</script>'}) == {'ok': True}
    assert observed['data'] == {'changes': {'text':'</script>'}}
    assert observed['key'] == 'fixed' and observed['default'] == {'ack': None}
