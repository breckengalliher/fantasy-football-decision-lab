from types import SimpleNamespace

from dashboard import qa_session_maintenance as maintenance
from streamlit.runtime.caching.ttl_cache import TTLCache


class FakeLoop:
    def __init__(self):
        self.callbacks = []

    def call_soon_threadsafe(self, callback):
        self.callbacks.append(callback)

    def drain(self):
        while self.callbacks:
            self.callbacks.pop(0)()


def fixture():
    clock = [0.0]
    cache = TTLCache(maxsize=128, ttl=120, timer=lambda: clock[0])
    shutdown = []
    cache['expired-private-id'] = SimpleNamespace(session=SimpleNamespace(shutdown=lambda: shutdown.append('expired')))
    clock[0] = 100
    cache['unexpired-private-id'] = SimpleNamespace(session=SimpleNamespace(shutdown=lambda: shutdown.append('unexpired')))
    clock[0] = 120
    manager = SimpleNamespace(_session_storage=SimpleNamespace(_cache=cache),
                              _active_session_info_by_id={'active-private-id': object()})
    loop = FakeLoop()
    fallback = []
    policy = maintenance.ExpiredSessionMaintenance(loop, manager, lambda: fallback.append(True))
    return policy, loop, cache, manager, shutdown, fallback


def test_only_elapsed_disconnected_entries_removed_on_eventloop():
    policy, loop, cache, manager, shutdown, fallback = fixture()
    policy.schedule()
    policy.schedule()
    assert len(loop.callbacks) == 1
    assert 'expired-private-id' in cache._data
    loop.drain()
    assert 'expired-private-id' not in cache._data
    assert 'unexpired-private-id' in cache._data
    assert 'active-private-id' in manager._active_session_info_by_id
    assert shutdown == ['expired'] and fallback == []
    assert cache.ttl == 120
    assert policy.stats()['expired_removed'] == 1
    assert 'private-id' not in str(policy.stats())
    policy.schedule()
    loop.drain()
    assert shutdown == ['expired']


def test_disable_before_queued_callback_preserves_every_owner():
    policy, loop, cache, _, shutdown, fallback = fixture()
    policy.schedule()
    policy.stop()
    loop.drain()
    assert len(cache._data) == 2 and shutdown == [] and fallback == []


def test_active_overlap_fails_closed_and_restores_cleanup():
    policy, loop, cache, manager, shutdown, fallback = fixture()
    manager._active_session_info_by_id['expired-private-id'] = object()
    policy.schedule()
    loop.drain()
    assert len(cache._data) == 2 and shutdown == [] and fallback == [True]
    assert policy.stats()['failure_latched']
    policy.schedule()
    assert loop.callbacks == []


def test_shutdown_error_is_coarse_and_restores_default():
    policy, loop, cache, _, _, fallback = fixture()
    cache._data['expired-private-id'].session.shutdown = lambda: (_ for _ in ()).throw(ValueError('private-account'))
    policy.schedule()
    loop.drain()
    assert policy.stats()['failure_type'] == 'ValueError'
    assert 'private-account' not in str(policy.stats())
    assert fallback == [True] and policy.stats()['stop_requested']


def test_scheduling_error_has_no_pending_queue_and_fails_closed():
    policy, loop, _, _, _, fallback = fixture()
    loop.call_soon_threadsafe = lambda fn: (_ for _ in ()).throw(RuntimeError('loop stopped'))
    policy.schedule()
    assert not policy.stats()['pending_callback'] and fallback == [True]


def test_portable_optin_requires_exact_nonempty_service_and_database(monkeypatch):
    env = {'SDL_SESSION_MAINTENANCE_POLICY':'expired', 'RENDER_SERVICE_ID':'future-service',
           'SUPABASE_URL':'https://future.example', 'SDL_CLEANUP_SERVICE_ID':'future-service',
           'SDL_CLEANUP_DATABASE_URL':'https://future.example'}
    assert maintenance.requested(env)
    assert not maintenance.requested({**env, 'SDL_CLEANUP_SERVICE_ID':'wrong'})
    assert not maintenance.requested({**env, 'SDL_CLEANUP_DATABASE_URL':'https://wrong.example'})
    assert not maintenance.requested({**env, 'RENDER_SERVICE_ID':' bad ', 'SDL_CLEANUP_SERVICE_ID':' bad '})
    assert not maintenance.requested({**env, 'SUPABASE_URL':'https://user:secret@future.example',
                                     'SDL_CLEANUP_DATABASE_URL':'https://user:secret@future.example'})
    assert not maintenance.requested({**env, 'SUPABASE_URL':'http://future.example',
                                     'SDL_CLEANUP_DATABASE_URL':'http://future.example'})
    assert not maintenance.requested({**env, 'SDL_QA_SESSION_MAINTENANCE':'expired', 'SDL_SESSION_MAINTENANCE_POLICY':''})


def test_install_hash_guard_refuses_worker(monkeypatch):
    monkeypatch.setattr(maintenance, '_REGISTRY', '_sdl_test_maintenance_hash')
    env = {'SDL_QA_SESSION_MAINTENANCE':'expired', 'RENDER_SERVICE_ID':maintenance.QA_SERVICE,
           'SUPABASE_URL':maintenance.QA_DATABASE}
    restored = []
    assert maintenance.install(environ=env, verifier=lambda:False, fallback=lambda: restored.append(True))['reason'] == 'framework-hash-mismatch'
    assert restored == [True]
    assert maintenance.install(environ=env, verifier=lambda:True)['failure_latched']
    assert maintenance.stats()['failure_latched']


def test_reconnect_boundaries_preserved_without_shortened_ttl():
    policy, loop, cache, _, shutdown, _ = fixture()
    # The unexpired owner can reconnect using the framework's normal read/delete.
    assert cache.get('unexpired-private-id') is not None
    del cache['unexpired-private-id']
    assert cache.get('expired-private-id') is None
    policy.schedule()
    loop.drain()
    assert shutdown == ['expired'] and cache.ttl == 120


def test_runtime_startup_failure_is_latched_and_restores_cleanup(monkeypatch):
    monkeypatch.setattr(maintenance, '_REGISTRY', '_sdl_test_maintenance_runtime_failure')
    env = {'SDL_QA_SESSION_MAINTENANCE':'expired', 'RENDER_SERVICE_ID':maintenance.QA_SERVICE,
           'SUPABASE_URL':maintenance.QA_DATABASE}
    restored = []
    runtime = SimpleNamespace(_get_async_objs=lambda: (_ for _ in ()).throw(RuntimeError('private-runtime')))
    result = maintenance.install(environ=env, verifier=lambda:True, runtime=runtime,
                                 fallback=lambda:restored.append(True))
    assert result['failure_type'] == 'RuntimeError' and result['failure_latched']
    assert restored == [True] and 'private-runtime' not in str(result)


def test_install_singleton_and_disable_drains_queued_noop(monkeypatch):
    monkeypatch.setattr(maintenance, '_REGISTRY', '_sdl_test_maintenance_singleton')
    monkeypatch.setattr(maintenance.ExpiredSessionMaintenance, 'start', lambda self:None)
    env = {'SDL_QA_SESSION_MAINTENANCE':'expired', 'RENDER_SERVICE_ID':maintenance.QA_SERVICE,
           'SUPABASE_URL':maintenance.QA_DATABASE}
    _, loop, cache, manager, shutdown, _ = fixture()
    runtime = SimpleNamespace(_get_async_objs=lambda:SimpleNamespace(eventloop=loop), _session_mgr=manager)
    maintenance.install(environ=env, verifier=lambda:True, runtime=runtime, fallback=lambda:None)
    installed = maintenance._registry().policy
    installed.schedule()
    maintenance.install(environ=env, verifier=lambda: (_ for _ in ()).throw(AssertionError('rehash')), runtime=runtime)
    assert maintenance._registry().policy is installed
    maintenance.disable()
    loop.drain()
    assert shutdown == [] and len(cache._data) == 2


def test_worker_start_failure_is_latched_without_joining_unstarted_thread(monkeypatch):
    monkeypatch.setattr(maintenance, '_REGISTRY', '_sdl_test_maintenance_start_failure')
    class FailedThread:
        def __init__(self, **kwargs):pass
        def start(self):raise RuntimeError('cannot start')
        def is_alive(self):return False
        def join(self, **kwargs):raise AssertionError('unstarted thread joined')
    monkeypatch.setattr(maintenance.threading, 'Thread', FailedThread)
    env = {'SDL_QA_SESSION_MAINTENANCE':'expired', 'RENDER_SERVICE_ID':maintenance.QA_SERVICE,
           'SUPABASE_URL':maintenance.QA_DATABASE}
    _, loop, _, manager, _, _ = fixture()
    runtime = SimpleNamespace(_get_async_objs=lambda:SimpleNamespace(eventloop=loop), _session_mgr=manager)
    restored = []
    result = maintenance.install(environ=env, verifier=lambda:True, runtime=runtime,
                                 fallback=lambda:restored.append(True))
    assert result['failure_latched'] and restored == [True]
