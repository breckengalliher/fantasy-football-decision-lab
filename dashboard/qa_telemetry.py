"""Bounded diagnostic instrumentation, enabled only on the named isolated QA service.

Never records credentials, widget values, queries, names, or roster contents.
Tracemalloc is explicitly controlled by a QA-container file and is not used for
ordinary performance measurements. No production instrumentation is enabled.
"""
import functools
import gc
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import tracemalloc
import uuid

QA_SERVICE = 'srv-db4ir249v7es7389sshg'
QA_URL = 'https://deburhwrnuqeyexpezzo.supabase.co'
PROFILE_FLAG = Path('/tmp/sdl-qa-profile')
DIAGNOSTIC_FLAG = Path('/tmp/sdl-qa-diagnostic')
CLEANUP_EXPERIMENT_FLAG = Path('/tmp/sdl-qa-cleanup-periodic')
DIAGNOSTIC_SINK = Path('/tmp/sdl-qa-diagnostic.jsonl')
DIAGNOSTIC_SINK_LIMIT = 8 * 1024 * 1024
RESOURCE_RECEIPT_FLAG = Path('/tmp/sdl-qa-resource-receipt')
RESOURCE_RECEIPT_SINK = Path('/tmp/sdl-qa-resource-receipt.jsonl')
RESOURCE_RECEIPT_LIMIT = 16 * 1024 * 1024
_resource_receipt_active = False
_resource_sink_stopped = False
_writer_cost = {mode: {'writes': 0, 'cpu_ms': 0.0, 'wall_ms': 0.0}
                for mode in ('diagnostic', 'resource-only')}
_sink_lock = threading.Lock()
_sink_stopped = False
_diagnostic_active = False
_diagnostic_lock = threading.RLock()
_gc_started = {}
_gc_totals = {generation: {'count': 0, 'duration_ms': 0.0,
                         'collected': 0, 'uncollectable': 0} for generation in range(3)}
_installed = False
_lock = threading.Lock()
_runs = 0
_active = 0


def enabled():
    return (os.getenv('RENDER_SERVICE_ID') == QA_SERVICE and
            os.getenv('SUPABASE_URL', '').rstrip('/') == QA_URL)


def emit(kind, **values):
    record = {'kind':kind,'epoch':time.time(),
              'source':os.getenv('RENDER_GIT_COMMIT','unknown'), **values}
    print('SDL_QA_TELEMETRY ' + json.dumps(record, separators=(',',':')), flush=True)
    _write_diagnostic_record(record)


def _write_diagnostic_record(record):
    """Preserve bounded QA receipt. Never overwrites prior diagnostics."""
    global _sink_stopped, _resource_sink_stopped
    if not (_diagnostic_active or _resource_receipt_active) or not enabled():
        return
    diagnostic = _diagnostic_active
    if (diagnostic and _sink_stopped) or (not diagnostic and _resource_sink_stopped):
        return
    if not diagnostic and record.get('kind') != 'resource':
        return
    wall_start = time.perf_counter()
    cpu_start = time.thread_time()
    mode = 'diagnostic' if diagnostic else 'resource-only'
    path = DIAGNOSTIC_SINK if diagnostic else RESOURCE_RECEIPT_SINK
    limit = DIAGNOSTIC_SINK_LIMIT if diagnostic else RESOURCE_RECEIPT_LIMIT
    # Only telemetry call sites supply these coarse records. No widget values,
    # environment dump, credentials, rows or exception messages are accepted.
    allowed = {'resource', 'run_start', 'run_end', 'profile_started',
               'profile_stopped', 'sampler_error'}
    if record.get('kind') not in allowed:
        return
    fields = {'kind', 'epoch', 'source', 'correlation', 'session', 'fragment',
              'processing_ms', 'state_key_count', 'profiling', 'completed_runs',
              'active_runs', 'diagnostic', 'memory.current', 'memory.peak',
              'memory.events', 'cpu.stat', 'process', 'data_cache_bytes',
              'resource_cache_bytes', 'data_cache_stat_groups',
              'resource_cache_stat_groups', 'traced_current_peak', 'allocation_top',
              'trace_snapshot_wall_ms', 'trace_snapshot_cpu_ms', 'trace_table_bytes',
              'error_type', 'cleanup', 'receipt_mode', 'receipt_writer_cost'}
    if not diagnostic:
        fields -= {'diagnostic', 'traced_current_peak', 'allocation_top',
                   'trace_snapshot_wall_ms', 'trace_snapshot_cpu_ms', 'trace_table_bytes'}
    bounded = {key: value for key, value in record.items() if key in fields}
    bounded['receipt_mode'] = mode
    encoded = (json.dumps(bounded, separators=(',', ':')) + '\n').encode('utf8')
    with _sink_lock:
        if (diagnostic and _sink_stopped) or (not diagnostic and _resource_sink_stopped):
            return
        try:
            size = path.stat().st_size if path.exists() else 0
            if size + len(encoded) > limit:
                raise OverflowError('diagnostic sink limit')
            with path.open('ab') as output:
                output.write(encoded)
            _writer_cost[mode]['writes'] += 1
        except (OSError, OverflowError) as error:
            if diagnostic:
                _sink_stopped = True
            else:
                _resource_sink_stopped = True
            # Do not recurse through emit/the failed sink or propagate into app.
            print('SDL_QA_TELEMETRY ' + json.dumps({'kind':'diagnostic_sink_stopped',
                  'epoch':time.time(),'error_type':type(error).__name__,
                  'receipt_mode':mode}), flush=True)
        finally:
            _writer_cost[mode]['cpu_ms'] += (time.thread_time()-cpu_start)*1000
            _writer_cost[mode]['wall_ms'] += (time.perf_counter()-wall_start)*1000


def _sync_resource_receipt():
    global _resource_receipt_active
    _resource_receipt_active = enabled() and RESOURCE_RECEIPT_FLAG.exists()
    return _resource_receipt_active


def receipt_writer_cost():
    with _sink_lock:
        return {mode: dict(value) for mode, value in _writer_cost.items()}


def resources():
    result = {}
    for name in ('memory.current','memory.peak','memory.events','cpu.stat'):
        try:
            value=Path('/sys/fs/cgroup', name).read_text().strip()
            result[name]=int(value) if value.isdigit() else dict(line.split() for line in value.splitlines())
        except (OSError,ValueError):pass
    try:
        result['process']=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines()
                               if line.startswith(('VmRSS:','VmHWM:','Threads:')))
    except OSError:pass
    return result


def _gc_callback(phase, info):
    """Observe automatic/framework GC only; bounded aggregate, no object values."""
    if not _diagnostic_active:
        return
    generation = info.get('generation')
    if generation not in _gc_totals:
        return
    key = (threading.get_ident(), generation)
    with _diagnostic_lock:
        if phase == 'start':
            if len(_gc_started) < 128:
                _gc_started[key] = time.perf_counter()
        elif phase == 'stop':
            start = _gc_started.pop(key, None)
            if start is not None:
                total = _gc_totals[generation]
                total['count'] += 1
                total['duration_ms'] += (time.perf_counter() - start) * 1000
                total['collected'] += info.get('collected', 0)
                total['uncollectable'] += info.get('uncollectable', 0)


def _sync_diagnostic():
    """Sampler owns registration. Removal does not collect or alter GC policy."""
    global _diagnostic_active
    requested = enabled() and DIAGNOSTIC_FLAG.exists()
    if requested and not _diagnostic_active:
        with _diagnostic_lock:
            _gc_started.clear()
            for total in _gc_totals.values():
                total.update(count=0, duration_ms=0.0, collected=0, uncollectable=0)
            _diagnostic_active = True
        if _gc_callback not in gc.callbacks:
            gc.callbacks.append(_gc_callback)
    elif not requested:
        _diagnostic_active = False
        if _gc_callback in gc.callbacks:
            gc.callbacks.remove(_gc_callback)
        with _diagnostic_lock:
            _gc_started.clear()
    return requested


def _session_ownership(manager):
    """Read raw storage only: TTL len()/values()/expire() can change ownership."""
    active = manager._active_session_info_by_id
    cache = manager._session_storage._cache
    # Guard the exact supported framework shape; do not fall back to mutating
    # public cache accessors when private implementation changes.
    data = cache._data
    expirations = cache._expirations
    if not isinstance(active, dict) or not isinstance(data, dict) or not isinstance(expirations, dict):
        raise TypeError('unsupported session storage')
    now = cache._timer()
    deadlines = tuple(expirations.values())
    return {'active_session_count': len(active),
            'disconnected_raw_count': len(data),
            'disconnected_expired_count': sum(deadline <= now for deadline in deadlines),
            'disconnected_live_count': sum(deadline > now for deadline in deadlines)}


def diagnostic_counts():
    if not _diagnostic_active:
        return {}
    wall = time.perf_counter()
    cpu = time.process_time()
    result = {}
    with _diagnostic_lock:
        result['gc_generations'] = {str(key): dict(value) for key, value in _gc_totals.items()}
    try:
        from streamlit.runtime import get_instance
        result.update(_session_ownership(get_instance()._session_mgr))
    except (AttributeError, TypeError, RuntimeError) as error:
        result['session_ownership_error'] = type(error).__name__
    try:
        import pyarrow as pa
        pool = pa.default_memory_pool()
        result['arrow_live_bytes'] = pool.bytes_allocated()
        result['arrow_peak_bytes'] = pool.max_memory()
    except (ImportError, AttributeError) as error:
        result['arrow_counter_error'] = type(error).__name__
    if tracemalloc.is_tracing():
        result['trace_table_bytes'] = tracemalloc.get_tracemalloc_memory()
    result['diagnostic_cpu_ms'] = (time.process_time() - cpu) * 1000
    result['diagnostic_wall_ms'] = (time.perf_counter() - wall) * 1000
    return result


def _sync_cleanup():
    # Normal sampler/install path only; never invoked from a GC callback.
    # Persistent activation requires the explicit QA environment flag. The
    # separate file is a reversible lead-controlled same-process experiment.
    if not enabled():
        return {'policy': 'framework-default'}
    try:
        from dashboard.qa_cleanup import install as configure
    except ModuleNotFoundError:
        from qa_cleanup import install as configure
    return configure(experiment=CLEANUP_EXPERIMENT_FLAG.exists())


def sample():
    ticks=0
    while True:
        try:
            cleanup = _sync_cleanup()
            _sync_diagnostic()
            _sync_resource_receipt()
            if PROFILE_FLAG.exists() and not tracemalloc.is_tracing():
                tracemalloc.start(1); emit('profile_started')
            elif not PROFILE_FLAG.exists() and tracemalloc.is_tracing():
                tracemalloc.stop();emit('profile_stopped')
            with _lock:counts={'completed_runs':_runs,'active_runs':_active}
            extra={'cleanup':cleanup}
            if _diagnostic_active or _resource_receipt_active:
                extra['receipt_writer_cost'] = receipt_writer_cost()
            if _diagnostic_active:
                extra['diagnostic'] = diagnostic_counts()
            if ticks % 6 == 0:
                from streamlit.runtime.caching.cache_data_api import _data_caches
                from streamlit.runtime.caching.cache_resource_api import _resource_caches
                for label,caches in (('data',_data_caches),('resource',_resource_caches)):
                    stats=[s for family in caches.get_stats().values() for s in family]
                    extra[label+'_cache_bytes']=sum(s.byte_length for s in stats)
                    # Streamlit groups statistics by cache function; this is
                    # not the number of individual cached objects.
                    extra[label+'_cache_stat_groups']=len(stats)
                if tracemalloc.is_tracing():
                    snapshot_start = time.perf_counter()
                    snapshot_cpu = time.process_time()
                    extra['traced_current_peak']=tracemalloc.get_traced_memory()
                    extra['allocation_top']=[{'file':str(s.traceback[0].filename).replace('/app/',''),
                      'line':s.traceback[0].lineno,'bytes':s.size,'count':s.count}
                      for s in tracemalloc.take_snapshot().statistics('lineno')[:8]]
                    extra['trace_snapshot_wall_ms'] = (time.perf_counter()-snapshot_start)*1000
                    extra['trace_snapshot_cpu_ms'] = (time.process_time()-snapshot_cpu)*1000
                    extra['trace_table_bytes'] = tracemalloc.get_tracemalloc_memory()
            emit('resource',profiling=tracemalloc.is_tracing(),**counts,**resources(),**extra)
        except Exception as error:
            emit('sampler_error',error_type=type(error).__name__)
        ticks+=1;time.sleep(5)


def install():
    global _installed
    if _installed or not enabled():return
    _installed=True
    _sync_cleanup()
    from streamlit.runtime.scriptrunner.script_runner import ScriptRunner
    original=ScriptRunner._run_script
    @functools.wraps(original)
    def measured(self, data):
        global _runs,_active
        correlation=uuid.uuid4().hex[:12]
        session=hashlib.sha256(str(self._session_id).encode()).hexdigest()[:12]
        start=time.perf_counter()
        with _lock:_active+=1
        emit('run_start',correlation=correlation,session=session,fragment=bool(data.fragment_id_queue))
        try:return original(self,data)
        finally:
            with _lock:_active-=1;_runs+=1
            try:
                ctx=self._get_script_run_ctx()
                state_keys=len(ctx.session_state.filtered_state)
            except Exception:state_keys=None
            emit('run_end',correlation=correlation,session=session,
                 processing_ms=round((time.perf_counter()-start)*1000,2),state_key_count=state_keys)
    ScriptRunner._run_script=measured
    emit('installed',**resources())
    threading.Thread(target=sample,name='sdl-qa-telemetry',daemon=True).start()
