from types import SimpleNamespace
import pytest
from dashboard import onboarding_storage as module


def test_exact_qa_bindings_required(monkeypatch):
    api = SimpleNamespace(url='https://deburhwrnuqeyexpezzo.supabase.co')
    monkeypatch.setenv('RENDER_SERVICE_ID', 'production')
    assert not module.enabled(api)
    monkeypatch.setenv('RENDER_SERVICE_ID', 'srv-db4ir249v7es7389sshg')
    assert module.enabled(api)
    assert not module.enabled(SimpleNamespace(url='https://other.supabase.co'))


@pytest.mark.parametrize('value,dismiss', [(None,False), ({'ok':True,'dismissed':False,'write_ack':False},True)])
def test_unacknowledged_preference_ends_render_without_polling(monkeypatch, value, dismiss):
    class Stop(Exception): pass
    monkeypatch.setattr(module, '_component', lambda: lambda **kw: SimpleNamespace(preference=value))
    monkeypatch.setattr(module.st, 'stop', lambda: (_ for _ in ()).throw(Stop()))
    with pytest.raises(Stop): module.load(dismiss=dismiss)


def test_dismissal_waits_for_ack_and_returns_true(monkeypatch):
    seen = {}
    def mount(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(preference={'ok':True,'dismissed':True,'write_ack':True})
    monkeypatch.setattr(module, '_component', lambda: mount)
    assert module.load(dismiss=True)
    assert seen['data'] == {'dismiss':True}
    assert seen['default'] == {'preference':None}


def test_unavailable_preference_reports_non_persistence(monkeypatch):
    messages = []
    monkeypatch.setattr(module, '_component', lambda: lambda **kw: SimpleNamespace(preference={'ok':False,'dismissed':True,'write_ack':True}))
    monkeypatch.setattr(module.st, 'caption', messages.append)
    assert module.load(dismiss=True)
    assert 'this visit only' in messages[0]
