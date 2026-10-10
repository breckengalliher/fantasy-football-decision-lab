"""Explicitly guarded, opt-in process-wide cleanup policy.

Normal app startup installs independently of QA telemetry; defaults remain off.
Standard Python automatic GC and thresholds remain untouched. No session or
cache is cleared. File experiments remain restricted to the named QA service.
"""
import atexit
import gc
import logging
import os
from pathlib import Path
import sys
import threading
import time
import types
from urllib.parse import urlsplit

QA_SERVICE = 'srv-db4ir249v7es7389sshg'
QA_DATABASE = 'https://deburhwrnuqeyexpezzo.supabase.co'
SUPPORTED_STREAMLIT = '1.65.0'
INTERVAL_SECONDS = 30.0
_REGISTRY = '_sdl_qa_cleanup_registry'
EXPERIMENT_FLAG = Path('/tmp/sdl-qa-cleanup-periodic')


def _log_failure(reason, error_type):
    # Fixed fields only: no exception messages, identities or environment values.
    registry = _registry()
    with registry.failure_lock:
        logged = getattr(registry, 'logged_failures', set())
        key = (reason, error_type)
        if key in logged or len(logged) >= 16:
            return
        logged.add(key)
        registry.logged_failures = logged
    logging.getLogger(__name__).warning(
        'SDL_CLEANUP_FAILURE reason=%s type=%s', reason, error_type)


def _valid_database(value):
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == 'https' and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def _registry():
    # Survives module aliases/reload; one process owns one cleanup worker.
    registry = types.ModuleType(_REGISTRY)
    registry.lock = threading.Lock()
    registry.failure_lock = threading.Lock()
    registry.policy = None
    return sys.modules.setdefault(_REGISTRY, registry)


class PeriodicCleanup:
    """One daemon, serialized generation-two collection, bounded idle delay.

    Python can still run its own automatic collections at any time. A failure
    restores Streamlit's extra per-script collection rather than leaving all
    full-heap cleanup suppressed. The caller starts this before changing config.
    """
    def __init__(self, collect, restore, *, interval=INTERVAL_SECONDS):
        self._collect = collect
        self._restore = restore
        self._interval = interval
        self._stop = threading.Event()
        self._armed = threading.Event()
        self._state_lock = threading.Lock()
        self._thread = None
        self._stats = dict(policy='periodic-qa-generation2', interval_seconds=interval,
                           collections=0, collected=0, collection_wall_ms=0.0,
                           maximum_collection_wall_ms=0.0, failure_type=None,
                           enabled=False, framework_restored=None, restore_failure_type=None,
                           automatic_gc_unchanged=True)

    def start(self):
        if self._thread is not None:
            raise RuntimeError('cleanup_worker_already_started')
        self._thread = threading.Thread(target=self._run, name='sdl-qa-periodic-gc', daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._armed.wait()
            while not self._stop.wait(self._interval):
                started = time.perf_counter()
                collected = self._collect(2)
                duration = (time.perf_counter()-started)*1000
                with self._state_lock:
                    self._stats['collections'] += 1
                    self._stats['collected'] += collected
                    self._stats['collection_wall_ms'] += duration
                    self._stats['maximum_collection_wall_ms'] = max(
                        self._stats['maximum_collection_wall_ms'], duration)
        except BaseException as error:
            with self._state_lock:
                self._stats['failure_type'] = type(error).__name__
            self._stop.set()
            self._restore_framework()
            _log_failure('collection-failed', type(error).__name__)

    def activate(self):
        with self._state_lock:
            self._stats['enabled'] = True
        self._armed.set()

    def fail_install(self, error):
        with self._state_lock:
            self._stats['failure_type'] = type(error).__name__

    def _restore_framework(self):
        try:
            restored = self._restore() is not False
            failure = None if restored else 'FrameworkRestoreRejected'
        except BaseException as error:
            restored, failure = False, type(error).__name__
        with self._state_lock:
            self._stats['enabled'] = False
            self._stats['framework_restored'] = restored
            self._stats['restore_failure_type'] = failure
        if failure:
            _log_failure('framework-restore-failed', failure)

    def stop(self):
        self._stop.set()
        self._armed.set()
        self._restore_framework()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def stats(self):
        with self._state_lock:
            result = dict(self._stats)
        result['worker_alive'] = self._thread is not None and self._thread.is_alive()
        result['stop_requested'] = self._stop.is_set()
        result['effective_policy'] = ('periodic-qa-generation2' if result['enabled']
            else 'automatic-python-only-framework-restore-failed' if result['framework_restored'] is False
            else 'framework-default')
        return result


def install(*, environ=None, config_api=None, gc_api=gc, version=None, experiment=None):
    """Explicitly opt-in only after exact-runtime diagnosis and lead approval.

    Fail closed to normal per-script cleanup. No hidden global config file,
    thresholds, automatic-GC enablement, session TTL, cache expiry or media
    cleanup behavior is modified. Persistent activation requires an explicit
    configured service/database match; QA file experiments cannot activate elsewhere.
    """
    env = os.environ if environ is None else environ
    registry = sys.modules.get(_REGISTRY)
    if registry is not None and getattr(registry, 'inhibited', False):
        return {**disable(), 'reason': 'session-maintenance-failure', 'inhibited': True}
    qa_identity = (env.get('RENDER_SERVICE_ID') == QA_SERVICE
                   and env.get('SUPABASE_URL', '').rstrip('/') == QA_DATABASE)
    if experiment is None:
        experiment = qa_identity and EXPERIMENT_FLAG.exists()
    generic_requested = env.get('SDL_CLEANUP_POLICY') == 'periodic'
    qa_requested = env.get('SDL_QA_CLEANUP_POLICY') == 'periodic' or experiment
    if generic_requested:
        service = env.get('SDL_CLEANUP_SERVICE_ID', '')
        database = env.get('SDL_CLEANUP_DATABASE_URL', '')
        if (not service or service.strip() != service or not _valid_database(database)
                or service != env.get('RENDER_SERVICE_ID')
                or database.rstrip('/') != env.get('SUPABASE_URL', '').rstrip('/')):
            result = disable()
            return {**result, 'reason': 'configured-identity-mismatch'}
    elif qa_requested:
        if not qa_identity:
            result = disable()
            return {**result, 'reason': 'qa-identity-mismatch'}
    else:
        return disable()
    if version is None:
        from importlib.metadata import version as package_version
        try:
            version = package_version('streamlit')
        except Exception as error:
            result = disable()
            _log_failure('runtime-version-read-failed', type(error).__name__)
            return {**result, 'reason': 'runtime-version-read-failed',
                    'failure_type': type(error).__name__}
    if version != SUPPORTED_STREAMLIT or not gc_api.isenabled():
        return {**disable(), 'reason': 'unsupported-runtime-or-disabled-auto-gc'}
    if config_api is None:
        from streamlit import config as config_api
    registry = _registry()
    with registry.lock:
        if getattr(registry, 'inhibited', False):
            current = registry.policy.stats() if registry.policy is not None else {'policy': 'framework-default'}
            return {**current, 'reason': 'session-maintenance-failure', 'inhibited': True}
        if registry.policy is not None:
            return registry.policy.stats()
        try:
            postscript_gc = config_api.get_option('runner.postScriptGC')
        except Exception as error:
            _log_failure('configuration-read-failed', type(error).__name__)
            return {'policy':'framework-default', 'reason':'configuration-read-failed',
                    'failure_type':type(error).__name__, 'enabled':False}
        if postscript_gc is not True:
            return {'policy': 'framework-default', 'reason': 'unexpected-postscript-setting'}
        def restore():
            config_api.set_option('runner.postScriptGC', True)
            return config_api.get_option('runner.postScriptGC') is True
        policy = PeriodicCleanup(gc_api.collect, restore)
        try:
            policy.start()
            config_api.set_option('runner.postScriptGC', False)
            if config_api.get_option('runner.postScriptGC') is not False:
                raise RuntimeError('cleanup_setting_not_applied')
            policy.activate()
        except BaseException as error:
            policy.fail_install(error)
            policy.stop()
            registry.policy = policy
            atexit.register(policy.stop)
            result = policy.stats()
            result['reason'] = 'installation-failed'
            _log_failure('installation-failed', type(error).__name__)
            return result
        registry.policy = policy
        atexit.register(policy.stop)
        return policy.stats()


def disable():
    """Restore normal framework GC, then stop the one worker outside the lock.

    Call only from normal sampler/install paths, never inside a GC callback.
    A subsequent explicit enable creates a worker only after the old one exits.
    Idempotent samples do not create workers or add atexit registrations.
    """
    registry = sys.modules.get(_REGISTRY)
    if registry is None:
        return {'policy': 'framework-default', 'reason': 'not-enabled'}
    with registry.lock:
        policy = registry.policy
    if policy is None:
        return {'policy': 'framework-default', 'reason': 'not-enabled'}
    policy.stop()
    with registry.lock:
        if registry.policy is policy and not policy.stats()['worker_alive']:
            registry.policy = None
            atexit.unregister(policy.stop)
    result = policy.stats()
    result['policy'] = 'framework-default'
    return result


def stats():
    registry = sys.modules.get(_REGISTRY)
    return ({'policy': 'framework-default'} if registry is None or registry.policy is None
            else registry.policy.stats())


def inhibit():
    """Latch maintenance failure until process restart; restore framework GC.

    Invoked outside maintenance locks. Later startup/sampler calls cannot
    re-enable periodic cleanup while expired-session maintenance is unhealthy.
    """
    registry = _registry()
    with registry.lock:
        registry.inhibited = True
    return {**disable(), 'reason': 'session-maintenance-failure', 'inhibited': True}
