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
