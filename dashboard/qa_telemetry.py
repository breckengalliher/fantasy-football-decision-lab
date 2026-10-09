"""Bounded diagnostic instrumentation, enabled only on the named isolated QA service.

Never records credentials, widget values, queries, names, or roster contents.
Tracemalloc is explicitly controlled by a QA-container file and is not used for
ordinary performance measurements. No production instrumentation is enabled.
"""
import functools
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
_installed = False
_lock = threading.Lock()
_runs = 0
_active = 0


def enabled():
    return (os.getenv('RENDER_SERVICE_ID') == QA_SERVICE and
            os.getenv('SUPABASE_URL', '').rstrip('/') == QA_URL)


def emit(kind, **values):
    print('SDL_QA_TELEMETRY ' + json.dumps({'kind':kind,'epoch':time.time(),
          'source':os.getenv('RENDER_GIT_COMMIT','unknown'), **values}, separators=(',',':')), flush=True)


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


def sample():
    ticks=0
    while True:
        try:
            if PROFILE_FLAG.exists() and not tracemalloc.is_tracing():
                tracemalloc.start(1); emit('profile_started')
            elif not PROFILE_FLAG.exists() and tracemalloc.is_tracing():
                tracemalloc.stop();emit('profile_stopped')
            with _lock:counts={'completed_runs':_runs,'active_runs':_active}
            extra={}
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
                    extra['traced_current_peak']=tracemalloc.get_traced_memory()
                    extra['allocation_top']=[{'file':str(s.traceback[0].filename).replace('/app/',''),
                      'line':s.traceback[0].lineno,'bytes':s.size,'count':s.count}
                      for s in tracemalloc.take_snapshot().statistics('lineno')[:8]]
            emit('resource',profiling=tracemalloc.is_tracing(),**counts,**resources(),**extra)
        except Exception as error:
            emit('sampler_error',error_type=type(error).__name__)
        ticks+=1;time.sleep(5)


def install():
    global _installed
    if _installed or not enabled():return
    _installed=True
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
