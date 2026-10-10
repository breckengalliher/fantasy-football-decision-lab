"""Opt-in identity guards, singleton lifecycle, automatic GC and failure fallback."""
import gc
import importlib
import sys
import threading
import time
import weakref

import pytest
from dashboard import qa_cleanup as cleanup


class Config:
    def __init__(self): self.value = True; self.changes = []
    def get_option(self, key): assert key == 'runner.postScriptGC'; return self.value
    def set_option(self, key, value):
        assert key == 'runner.postScriptGC'
        self.value = value
        self.changes.append(value)


def environment():
    return dict(SDL_QA_CLEANUP_POLICY='periodic', RENDER_SERVICE_ID=cleanup.QA_SERVICE,
                SUPABASE_URL=cleanup.QA_DATABASE)


@pytest.fixture(autouse=True)
def isolated_policy():
    registry = sys.modules.pop(cleanup._REGISTRY, None)
    assert registry is None or registry.policy is None
    yield
    registry = sys.modules.pop(cleanup._REGISTRY, None)
    if registry is not None and registry.policy is not None:
        registry.policy.stop()


def test_default_wrong_service_database_and_version_do_not_change_framework():
    for env, version in [(dict(), cleanup.SUPPORTED_STREAMLIT),
                         ({**environment(), 'RENDER_SERVICE_ID': 'production'}, cleanup.SUPPORTED_STREAMLIT),
                         ({**environment(), 'SUPABASE_URL': 'https://production.invalid'}, cleanup.SUPPORTED_STREAMLIT),
                         (environment(), 'different')]:
        config = Config()
        assert cleanup.install(environ=env, config_api=config, version=version)['policy'] == 'framework-default'
        assert config.value is True and not config.changes
        assert cleanup._REGISTRY not in sys.modules


def test_install_singleton_survives_parallel_callers_and_module_reload():
    config = Config()
    thresholds = gc.get_threshold()
    enabled = gc.isenabled()
    threads = [threading.Thread(target=lambda: cleanup.install(
        environ=environment(), config_api=config, version=cleanup.SUPPORTED_STREAMLIT)) for _ in range(8)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    policy = sys.modules[cleanup._REGISTRY].policy
    assert config.changes == [False] and policy.stats()['worker_alive']
    importlib.reload(cleanup)
    cleanup.install(environ=environment(), config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    assert sys.modules[cleanup._REGISTRY].policy is policy and config.changes == [False]
    assert gc.get_threshold() == thresholds and gc.isenabled() == enabled
    policy.stop()
    assert config.value is True and not policy.stats()['worker_alive']


def test_periodic_worker_collects_cycles_without_disabling_automatic_gc():
    class Cycle: pass
    item = Cycle(); item.self = item
    reference = weakref.ref(item)
    del item
    restored = threading.Event()
    policy = cleanup.PeriodicCleanup(gc.collect, restored.set, interval=0.02)
    enabled = gc.isenabled(); thresholds = gc.get_threshold()
    policy.start(); policy.activate()
    try:
        deadline = time.monotonic() + 2
        while (reference() is not None or policy.stats()['collections'] == 0) and time.monotonic() < deadline:
            time.sleep(0.005)
        assert reference() is None and policy.stats()['collections'] >= 1
        assert gc.isenabled() == enabled and gc.get_threshold() == thresholds
    finally:
        policy.stop()
    assert restored.is_set() and not policy.stats()['worker_alive']


def test_collector_failure_restores_framework_cleanup():
    config = Config(); config.value = False
    restored = threading.Event()
    def fail(generation):
        assert generation == 2
        raise RuntimeError('bounded_test_failure')
    def restore(): config.set_option('runner.postScriptGC', True); restored.set()
    policy = cleanup.PeriodicCleanup(fail, restore, interval=0.01)
    policy.start(); policy.activate()
    assert restored.wait(2)
    policy.stop()
    assert config.value is True and policy.stats()['failure_type'] == 'RuntimeError'


def test_config_install_failure_stops_worker_and_restores_default():
    class Reject(Config):
        def set_option(self, key, value):
            if value is False: raise RuntimeError('cannot_change_setting')
            super().set_option(key, value)
    config = Reject()
    result = cleanup.install(environ=environment(), config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    assert result['reason'] == 'installation-failed' and result['failure_type'] == 'RuntimeError'
    assert not result['enabled'] and result['framework_restored']
    assert config.value is True and not sys.modules[cleanup._REGISTRY].policy.stats()['worker_alive']


def test_existing_external_disabled_postscript_setting_is_not_overridden():
    config = Config(); config.value = False
    result = cleanup.install(environ=environment(), config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    assert result['reason'] == 'unexpected-postscript-setting'
    assert config.changes == [] and sys.modules[cleanup._REGISTRY].policy is None


def test_reversible_file_experiment_restores_default_and_reenable_is_singleton():
    config = Config()
    env = environment(); env.pop('SDL_QA_CLEANUP_POLICY')
    cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT, experiment=True)
    original = sys.modules[cleanup._REGISTRY].policy
    cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT, experiment=True)
    assert config.changes == [False]
    cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT, experiment=False)
    assert config.value is True and not original.stats()['worker_alive']
    assert sys.modules[cleanup._REGISTRY].policy is None
    cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT, experiment=True)
    assert sys.modules[cleanup._REGISTRY].policy is not original
    assert config.changes.count(False) == 2


def test_persistent_qa_mode_survives_experiment_flag_removal():
    config = Config()
    cleanup.install(environ=environment(), config_api=config, version=cleanup.SUPPORTED_STREAMLIT, experiment=True)
    policy = sys.modules[cleanup._REGISTRY].policy
    cleanup.install(environ=environment(), config_api=config, version=cleanup.SUPPORTED_STREAMLIT, experiment=False)
    assert sys.modules[cleanup._REGISTRY].policy is policy and config.changes == [False]


def test_restore_failure_is_explicit_and_does_not_escape_worker_or_stop():
    def fail(generation): raise RuntimeError('collector_failure')
    def restore(): raise ValueError('restore_failure')
    policy = cleanup.PeriodicCleanup(fail, restore, interval=0.01)
    policy.start(); policy.activate()
    deadline = time.monotonic()+2
    while policy.stats()['worker_alive'] and time.monotonic()<deadline:
        time.sleep(0.005)
    policy.stop()
    result = policy.stats()
    assert not result['enabled'] and result['framework_restored'] is False
    assert result['restore_failure_type']=='ValueError'
    assert result['effective_policy']=='automatic-python-only-framework-restore-failed'


def test_disabled_python_gc_rejects_policy_without_altering_framework():
    class DisabledGC:
        @staticmethod
        def isenabled(): return False
    config=Config()
    result=cleanup.install(environ=environment(),config_api=config,gc_api=DisabledGC,version=cleanup.SUPPORTED_STREAMLIT)
    assert result['reason']=='unsupported-runtime-or-disabled-auto-gc' and not config.changes


def test_worker_start_failure_is_coarse_and_restores_framework(monkeypatch):
    def fail(self): raise OSError('start_failed')
    monkeypatch.setattr(cleanup.PeriodicCleanup,'start',fail)
    config=Config()
    result=cleanup.install(environ=environment(),config_api=config,version=cleanup.SUPPORTED_STREAMLIT)
    assert result['failure_type']=='OSError' and result['framework_restored'] is True
    assert not result['enabled'] and config.value is True


def test_config_read_failure_remains_default_without_starting_worker():
    class Reject(Config):
        def get_option(self,key): raise KeyError('missing_option')
    config=Reject()
    result=cleanup.install(environ=environment(),config_api=config,version=cleanup.SUPPORTED_STREAMLIT)
    assert result['reason']=='configuration-read-failed' and result['failure_type']=='KeyError'
    assert not result['enabled'] and not config.changes


def configured_environment():
    return dict(SDL_CLEANUP_POLICY='periodic', SDL_CLEANUP_SERVICE_ID='explicit-service',
                SDL_CLEANUP_DATABASE_URL='https://explicit.supabase.co',
                RENDER_SERVICE_ID='explicit-service', SUPABASE_URL='https://explicit.supabase.co')


@pytest.mark.parametrize('field,value', [
    ('SDL_CLEANUP_SERVICE_ID', ''), ('SDL_CLEANUP_SERVICE_ID', ' other '),
    ('SDL_CLEANUP_DATABASE_URL', ''), ('SDL_CLEANUP_DATABASE_URL', 'http://explicit.supabase.co'),
    ('SDL_CLEANUP_DATABASE_URL', 'https://user:secret@explicit.supabase.co'),
    ('RENDER_SERVICE_ID', 'different-service'), ('SUPABASE_URL', 'https://different.supabase.co')])
def test_generic_incomplete_or_mismatched_identity_preserves_framework(field, value):
    env = {**configured_environment(), field: value}; config = Config()
    result = cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    assert result['reason'] == 'configured-identity-mismatch'
    assert config.value is True and config.changes == []


def test_generic_nonqa_install_and_telemetry_false_experiment_share_same_worker():
    config = Config(); env = configured_environment()
    cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    policy = sys.modules[cleanup._REGISTRY].policy
    cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT, experiment=False)
    assert sys.modules[cleanup._REGISTRY].policy is policy and config.changes == [False]
    assert gc.isenabled()


def test_qa_experiment_cannot_enable_configured_nonqa_identity_without_policy():
    env = configured_environment(); env.pop('SDL_CLEANUP_POLICY'); config = Config()
    result = cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT, experiment=True)
    assert result['reason'] == 'qa-identity-mismatch' and config.changes == []


def test_inhibit_restores_framework_and_latches_across_reinstall():
    env = configured_environment(); config = Config()
    cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    result = cleanup.inhibit()
    assert result['inhibited'] and config.value is True
    result = cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    assert result['inhibited'] and config.changes == [False, True]


def test_failure_logging_is_coarse_and_deduplicated(caplog):
    class Reject(Config):
        def get_option(self, key): raise KeyError('secret-account-and-database')
    for _ in range(2):
        cleanup.install(environ=configured_environment(), config_api=Reject(), version=cleanup.SUPPORTED_STREAMLIT)
    assert len(caplog.records) == 1
    assert 'configuration-read-failed' in caplog.text and 'KeyError' in caplog.text
    assert 'secret-account' not in caplog.text and 'explicit.supabase' not in caplog.text


def test_generic_runtime_guard_and_identity_drift_restore_framework():
    config = Config(); env = configured_environment()
    cleanup.install(environ=env, config_api=config, version='unsupported')
    assert not config.changes
    cleanup.install(environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    result = cleanup.install(environ={**env, 'RENDER_SERVICE_ID': 'changed'},
                             config_api=config, version=cleanup.SUPPORTED_STREAMLIT)
    assert result['reason'] == 'configured-identity-mismatch'
    assert config.value is True and config.changes == [False, True]


def test_app_startup_installs_policy_even_when_qa_telemetry_is_inactive(monkeypatch):
    import ast
    from pathlib import Path
    import types
    calls = []
    config = Config()
    original = cleanup.install
    def install():
        calls.append('cleanup')
        return original(environ=configured_environment(), config_api=config,
                        version=cleanup.SUPPORTED_STREAMLIT)
    monkeypatch.setattr(cleanup, 'install', install)
    telemetry = types.ModuleType('dashboard.qa_telemetry')
    telemetry.install = lambda: calls.append('inactive-qa-telemetry')
    monkeypatch.setitem(sys.modules, 'dashboard.qa_telemetry', telemetry)
    maintenance = types.ModuleType('dashboard.qa_session_maintenance')
    maintenance.install = lambda **kwargs: calls.append('maintenance')
    monkeypatch.setitem(sys.modules, 'dashboard.qa_session_maintenance', maintenance)
    tree = ast.parse((Path(__file__).parents[1] / 'dashboard/app.py').read_text(encoding='utf8'))
    startup = []
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            break
        startup.append(statement)
    exec(compile(ast.fix_missing_locations(ast.Module(body=startup, type_ignores=[])),
                 'app-startup', 'exec'), {})
    assert calls == ['cleanup', 'maintenance', 'inactive-qa-telemetry']
    assert config.value is False and sys.modules[cleanup._REGISTRY].policy.stats()['enabled']


def test_inhibit_is_rechecked_before_worker_install(monkeypatch):
    config = Config()
    original = cleanup._registry
    def inhibited_registry():
        registry = original()
        registry.inhibited = True
        return registry
    monkeypatch.setattr(cleanup, '_registry', inhibited_registry)
    result = cleanup.install(environ=configured_environment(), config_api=config,
                             version=cleanup.SUPPORTED_STREAMLIT)
    assert result['inhibited'] and config.changes == []


def test_maintenance_failure_inhibits_periodic_through_telemetry_resolver(monkeypatch):
    from dashboard import qa_session_maintenance as maintenance
    from dashboard import qa_telemetry as telemetry
    env = {**environment(), 'SDL_QA_SESSION_MAINTENANCE': 'expired'}
    config = Config()
    original_cleanup = cleanup.install
    original_maintenance = maintenance.install
    monkeypatch.setattr(maintenance, '_REGISTRY', '_sdl_maintenance_cleanup_integration')
    monkeypatch.setattr(cleanup, 'install', lambda **kwargs: original_cleanup(
        environ=env, config_api=config, version=cleanup.SUPPORTED_STREAMLIT, **kwargs))
    monkeypatch.setattr(maintenance, 'install', lambda **kwargs: original_maintenance(
        environ=env, verifier=lambda: False, **kwargs))
    monkeypatch.setattr(telemetry, 'enabled', lambda: True)
    assert telemetry._sync_cleanup()['enabled'] and config.value is False
    assert telemetry._sync_session_maintenance()['failure_latched']
    result = telemetry._sync_cleanup()
    assert result['inhibited'] and config.value is True
    assert config.changes == [False, True]
