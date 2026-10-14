"""Opt-in physical release of naturally expired disconnected sessions.

No active/unexpired session, TTL, automatic GC threshold or public cache changes.
All storage mutation/shutdown runs on the runtime event loop, never the daemon.
"""
import atexit
import hashlib
import importlib
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
EXPERIMENT_FLAG = Path('/tmp/sdl-qa-session-maintenance')
_REGISTRY = '_sdl_session_maintenance_registry'
FRAMEWORK_HASHES = {
    'streamlit.runtime.caching.ttl_cache': 'ea6994eb62a080ac4e3f379f7ff00d33e6f9666df764e553ceab2244435c0ca2',
    'streamlit.runtime.memory_session_storage': 'fd9bd10c15ba72b6af64e386d12f732ca707f2e8e6ca29abaa60b0d4c422a74a',
    'streamlit.runtime.websocket_session_manager': '31b40aa75afac7159709161d0280596a1dafeba211a212aba9359c29820aace9',
    'streamlit.runtime.app_session': '91d8a0de1d80a25beddd4895d44def328973fe1b1b74b03b266fe3d0acfbaab7',
    'streamlit.runtime.runtime': 'b7ffac40ef3d25111f5416f76fe759f0bd2abfad2fc18c54b4b0f892fb3a1d07',
}


def framework_verified():
    try:
        return all(hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest() == digest
                   for name, digest in FRAMEWORK_HASHES.items())
    except (ImportError, OSError, TypeError):
        return False


def requested(environ=None):
    env = os.environ if environ is None else environ
    service = env.get('RENDER_SERVICE_ID', '')
    database = env.get('SUPABASE_URL', '').rstrip('/')
    try:
        parsed = urlsplit(database)
        valid_database = (parsed.scheme == 'https' and bool(parsed.hostname)
                          and not parsed.username and not parsed.password
                          and not parsed.query and not parsed.fragment
                          and parsed.path in ('', '/') and not any(ch.isspace() for ch in database))
    except ValueError:
        valid_database = False
    portable = (env.get('SDL_SESSION_MAINTENANCE_POLICY') == 'expired'
                and bool(service) and bool(database)
                and service.strip() == service and not any(ch.isspace() for ch in service)
                and valid_database
                and env.get('SDL_CLEANUP_SERVICE_ID') == service
                and env.get('SDL_CLEANUP_DATABASE_URL', '').rstrip('/') == database)
    qa = (service == QA_SERVICE and database == QA_DATABASE
          and (env.get('SDL_QA_SESSION_MAINTENANCE') == 'expired' or EXPERIMENT_FLAG.exists()))
    return portable or qa


def _registry():
    registry = types.ModuleType(_REGISTRY)
    registry.lock = threading.Lock()
    registry.policy = None
    registry.failure_latched = False
    return sys.modules.setdefault(_REGISTRY, registry)


class ExpiredSessionMaintenance:
    def __init__(self, loop, manager, fallback, *, interval=10):
        self._loop = loop
        self._manager = manager
        self._fallback = fallback
        self._interval = interval
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._pending = False
        self._thread = None
        self._counts = {'policy': 'expired-disconnected', 'callbacks': 0,
                        'expired_removed': 0, 'shutdown_count': 0,
                        'callback_wall_ms': 0.0, 'callback_cpu_ms': 0.0,
                        'failure_type': None, 'failure_latched': False}

    def _fail(self, error):
        self._stop.set()
        with self._lock:
            self._counts['failure_type'] = type(error).__name__
            self._counts['failure_latched'] = True
        logging.getLogger(__name__).warning('SDL_SESSION_MAINTENANCE_FAILURE type=%s', type(error).__name__)
        # Never call fallback under storage/state locks or from a GC callback.
        try:
            self._fallback()
        except Exception:
            pass

    def schedule(self):
        with self._lock:
            if self._stop.is_set() or self._pending:
                return
            self._pending = True
        try:
            self._loop.call_soon_threadsafe(self._release_expired)
        except Exception as error:
            with self._lock:
                self._pending = False
            self._fail(error)

    def _release_expired(self):
        removed = []
        wall = time.perf_counter()
        cpu = time.thread_time()
        try:
            if self._stop.is_set():
                return
            cache = self._manager._session_storage._cache
            active = self._manager._active_session_info_by_id
            if (not isinstance(cache._data, dict) or not isinstance(cache._expirations, dict)
                    or not isinstance(active, dict) or cache.ttl != 120 or cache.maxsize != 128):
                raise RuntimeError('unsupported-session-storage')
            now = cache._timer()
            expired = [key for key, deadline in cache._expirations.items() if deadline <= now]
            if any(key in active for key in expired):
                raise RuntimeError('active-storage-overlap')
            removed = cache.expire(now)
            with self._lock:
                self._counts['callbacks'] += 1
                self._counts['expired_removed'] += len(removed)
            shutdown_error = None
            for _, info in removed:
                try:
                    info.session.shutdown()
                    with self._lock:
                        self._counts['shutdown_count'] += 1
                except Exception as error:
                    shutdown_error = error
            if shutdown_error is not None:
                raise shutdown_error
        except Exception as error:
            self._fail(error)
        finally:
            removed.clear()
            with self._lock:
                self._pending = False
                self._counts['callback_wall_ms'] += (time.perf_counter()-wall)*1000
                self._counts['callback_cpu_ms'] += (time.thread_time()-cpu)*1000

    def _run(self):
        while not self._stop.wait(self._interval):
            self.schedule()

    def start(self):
        self._thread = threading.Thread(target=self._run, name='sdl-expired-session-maintenance', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if (self._thread is not None and self._thread is not threading.current_thread()
                and self._thread.is_alive()):
            self._thread.join(timeout=2)

    def stats(self):
        with self._lock:
            result = dict(self._counts)
            result['pending_callback'] = self._pending
        result['worker_alive'] = self._thread is not None and self._thread.is_alive()
        result['stop_requested'] = self._stop.is_set()
        return result


def install(*, fallback=None, environ=None, runtime=None, verifier=framework_verified):
    if not requested(environ):
        return disable()
    registry = _registry()
    with registry.lock:
        if registry.failure_latched:
            return {'policy': 'disabled', 'failure_latched': True}
        if registry.policy is not None:
            return registry.policy.stats()
    if fallback is None:
        from streamlit import config
        fallback = lambda: config.set_option('runner.postScriptGC', True)
    def failed():
        with registry.lock:
            registry.failure_latched = True
        logging.getLogger(__name__).warning('SDL_SESSION_MAINTENANCE_FALLBACK policy=framework-default failure_latched=True')
        try:
            fallback()
        except Exception:
            from streamlit import config
            config.set_option('runner.postScriptGC', True)
    if not verifier():
        failed()
        return {'policy': 'disabled', 'reason': 'framework-hash-mismatch', 'failure_latched': True}
    try:
        if runtime is None:
            from streamlit.runtime import get_instance
            runtime = get_instance()
        policy = ExpiredSessionMaintenance(runtime._get_async_objs().eventloop, runtime._session_mgr, failed)
    except Exception as error:
        failed()
        return {'policy': 'disabled', 'failure_type': type(error).__name__, 'failure_latched': True}
    start_error = None
    with registry.lock:
        if registry.failure_latched:
            return {'policy': 'disabled', 'failure_latched': True}
        if registry.policy is not None:
            return registry.policy.stats()
        try:
            policy.start()
            registry.policy = policy
            atexit.register(policy.stop)
        except Exception as error:
            start_error = error
    if start_error is not None:
        policy.stop()
        failed()
        return {'policy': 'disabled', 'failure_type': type(start_error).__name__, 'failure_latched': True}
    return policy.stats()


def disable():
    registry = sys.modules.get(_REGISTRY)
    if registry is None:
        return {'policy': 'disabled'}
    with registry.lock:
        policy = registry.policy
    if policy is not None:
        policy.stop()
        with registry.lock:
            if registry.policy is policy and not policy.stats()['worker_alive']:
                registry.policy = None
                atexit.unregister(policy.stop)
    return {'policy': 'disabled', 'failure_latched': registry.failure_latched}


def stats():
    registry = sys.modules.get(_REGISTRY)
    if registry is None:
        return {'policy': 'disabled'}
    with registry.lock:
        policy = registry.policy
        latched = registry.failure_latched
    return ({'policy': 'disabled', 'failure_latched': latched}
            if policy is None else policy.stats())
