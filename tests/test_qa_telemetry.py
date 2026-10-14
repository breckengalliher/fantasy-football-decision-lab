from dashboard import qa_telemetry


def test_raw_session_ownership_does_not_reap_expired_or_log_values():
    from types import SimpleNamespace
    from streamlit.runtime.caching.ttl_cache import TTLCache
    clock = [0.0]
    cache = TTLCache(maxsize=128, ttl=120, timer=lambda: clock[0])
    cache['private-session'] = {'private-token': 'secret'}
    clock[0] = 425.0
    manager = SimpleNamespace(_active_session_info_by_id={},
                              _session_storage=SimpleNamespace(_cache=cache))
    result = qa_telemetry._session_ownership(manager)
    assert result == {'active_session_count': 0, 'disconnected_raw_count': 1,
                      'disconnected_expired_count': 1, 'disconnected_live_count': 0}
    assert len(cache._data) == 1
    assert 'private' not in str(result) and 'secret' not in str(result)


def test_diagnostic_flag_registers_aggregates_and_removes_callback(monkeypatch, tmp_path):
    flag = tmp_path / 'diagnostic'
    monkeypatch.setattr(qa_telemetry, 'DIAGNOSTIC_FLAG', flag)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: True)
    monkeypatch.setattr(qa_telemetry.gc, 'callbacks', [])
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', False)
    assert not qa_telemetry._sync_diagnostic()
    assert qa_telemetry.gc.callbacks == []
    flag.touch()
    assert qa_telemetry._sync_diagnostic()
    assert qa_telemetry.gc.callbacks == [qa_telemetry._gc_callback]
    qa_telemetry._sync_diagnostic()
    assert len(qa_telemetry.gc.callbacks) == 1
    qa_telemetry._gc_callback('start', {'generation': 2})
    qa_telemetry._gc_callback('stop', {'generation': 2, 'collected': 7, 'uncollectable': 0})
    assert qa_telemetry._gc_totals[2]['count'] == 1
    assert qa_telemetry._gc_totals[2]['collected'] == 7
    assert qa_telemetry._gc_totals[2]['duration_ms'] >= 0
    flag.unlink()
    assert not qa_telemetry._sync_diagnostic()
    assert qa_telemetry.gc.callbacks == []
    assert qa_telemetry.diagnostic_counts() == {}


def test_diagnostic_flag_cannot_enable_outside_qa(monkeypatch, tmp_path):
    flag = tmp_path / 'diagnostic'
    flag.touch()
    monkeypatch.setattr(qa_telemetry, 'DIAGNOSTIC_FLAG', flag)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: False)
    monkeypatch.setattr(qa_telemetry.gc, 'callbacks', [])
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', False)
    assert not qa_telemetry._sync_diagnostic()
    assert qa_telemetry.gc.callbacks == []


def test_diagnostic_sink_disabled_and_nonqa_never_writes(monkeypatch, tmp_path):
    path = tmp_path / 'receipt.jsonl'
    monkeypatch.setattr(qa_telemetry, 'DIAGNOSTIC_SINK', path)
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', False)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: True)
    qa_telemetry.emit('run_end', state_key_count=1)
    assert not path.exists()
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', True)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: False)
    qa_telemetry.emit('run_end', state_key_count=1)
    assert not path.exists()


def test_diagnostic_sink_preserves_prior_receipt_and_stops_at_bound(monkeypatch, tmp_path, capsys):
    import json
    path = tmp_path / 'receipt.jsonl'
    path.write_bytes(b'prior-receipt\n')
    monkeypatch.setattr(qa_telemetry, 'DIAGNOSTIC_SINK', path)
    monkeypatch.setattr(qa_telemetry, 'DIAGNOSTIC_SINK_LIMIT', 220)
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', True)
    monkeypatch.setattr(qa_telemetry, '_sink_stopped', False)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: True)
    qa_telemetry._write_diagnostic_record({'kind':'run_end', 'epoch':1,
        'state_key_count':2, 'private-token':'do-not-record'})
    first = path.read_bytes()
    assert first.startswith(b'prior-receipt\n')
    assert b'private-token' not in first and b'do-not-record' not in first
    assert json.loads(first.splitlines()[1])['state_key_count'] == 2
    for _ in range(10):
        qa_telemetry._write_diagnostic_record({'kind':'run_end', 'epoch':1,
            'state_key_count':2})
    assert path.stat().st_size <= 220
    assert qa_telemetry._sink_stopped
    before = path.read_bytes()
    qa_telemetry._write_diagnostic_record({'kind':'run_end', 'epoch':2})
    assert path.read_bytes() == before
    assert capsys.readouterr().out.count('diagnostic_sink_stopped') == 1


def test_diagnostic_sink_failure_does_not_break_emit(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(qa_telemetry, 'DIAGNOSTIC_SINK', tmp_path / 'missing' / 'receipt')
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', True)
    monkeypatch.setattr(qa_telemetry, '_sink_stopped', False)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: True)
    qa_telemetry.emit('run_end', state_key_count=1)
    qa_telemetry.emit('run_end', state_key_count=2)
    assert capsys.readouterr().out.count('diagnostic_sink_stopped') == 1


def test_resource_receipt_flag_is_independent_and_records_only_resources(monkeypatch, tmp_path):
    import json
    path = tmp_path / 'resources.jsonl'
    flag = tmp_path / 'resource-flag'
    flag.touch()
    monkeypatch.setattr(qa_telemetry, 'RESOURCE_RECEIPT_FLAG', flag)
    monkeypatch.setattr(qa_telemetry, 'RESOURCE_RECEIPT_SINK', path)
    monkeypatch.setattr(qa_telemetry, '_resource_receipt_active', False)
    monkeypatch.setattr(qa_telemetry, '_resource_sink_stopped', False)
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', False)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: True)
    callbacks = list(qa_telemetry.gc.callbacks)
    assert qa_telemetry._sync_resource_receipt()
    assert not qa_telemetry._diagnostic_active
    assert list(qa_telemetry.gc.callbacks) == callbacks
    assert qa_telemetry.diagnostic_counts() == {}
    qa_telemetry.emit('run_start', session='private-session')
    assert not path.exists()
    qa_telemetry.emit('resource', completed_runs=42, profiling=False,
                      cleanup={'policy':'framework-default'},
                      diagnostic={'do-not-record':'secret'}, private_token='secret')
    record = json.loads(path.read_text())
    assert record['receipt_mode'] == 'resource-only'
    assert record['completed_runs'] == 42
    assert record['cleanup']['policy'] == 'framework-default'
    assert 'diagnostic' not in record and 'secret' not in path.read_text()
    assert qa_telemetry.receipt_writer_cost()['resource-only']['writes'] >= 1
    assert qa_telemetry.receipt_writer_cost()['resource-only']['cpu_ms'] >= 0
    flag.unlink()
    assert not qa_telemetry._sync_resource_receipt()
    before = path.read_bytes()
    qa_telemetry.emit('resource', completed_runs=43)
    assert path.read_bytes() == before


def test_resource_receipt_nonqa_and_size_limit_preserve_prior(monkeypatch, tmp_path, capsys):
    path = tmp_path / 'resources.jsonl'
    path.write_bytes(b'prior\n')
    monkeypatch.setattr(qa_telemetry, 'RESOURCE_RECEIPT_SINK', path)
    monkeypatch.setattr(qa_telemetry, 'RESOURCE_RECEIPT_LIMIT', 12)
    monkeypatch.setattr(qa_telemetry, '_resource_receipt_active', True)
    monkeypatch.setattr(qa_telemetry, '_resource_sink_stopped', False)
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', False)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: False)
    qa_telemetry._write_diagnostic_record({'kind':'resource'})
    assert path.read_bytes() == b'prior\n'
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: True)
    qa_telemetry._write_diagnostic_record({'kind':'resource'})
    qa_telemetry._write_diagnostic_record({'kind':'resource'})
    assert path.read_bytes() == b'prior\n'
    assert capsys.readouterr().out.count('diagnostic_sink_stopped') == 1
    assert qa_telemetry._resource_sink_stopped


def test_instrumentation_requires_exact_qa_service_and_database(monkeypatch):
    monkeypatch.delenv('RENDER_SERVICE_ID',raising=False)
    monkeypatch.setenv('SUPABASE_URL',qa_telemetry.QA_URL)
    assert not qa_telemetry.enabled()
    monkeypatch.setenv('RENDER_SERVICE_ID',qa_telemetry.QA_SERVICE)
    assert qa_telemetry.enabled()
    monkeypatch.setenv('SUPABASE_URL','https://vpcnkspovsfdlzzrtxjc.supabase.co')
    assert not qa_telemetry.enabled()


def test_disabled_install_does_not_start_thread_or_trace(monkeypatch):
    monkeypatch.delenv('RENDER_SERVICE_ID',raising=False)
    monkeypatch.setattr(qa_telemetry.threading,'Thread',lambda **kwargs: (_ for _ in ()).throw(AssertionError('thread started')))
    qa_telemetry.install()


def test_resource_receipt_preserves_coarse_session_maintenance_status(monkeypatch, tmp_path):
    import json
    path = tmp_path / 'maintenance-resources.jsonl'
    monkeypatch.setattr(qa_telemetry, 'RESOURCE_RECEIPT_SINK', path)
    monkeypatch.setattr(qa_telemetry, '_resource_receipt_active', True)
    monkeypatch.setattr(qa_telemetry, '_resource_sink_stopped', False)
    monkeypatch.setattr(qa_telemetry, '_diagnostic_active', False)
    monkeypatch.setattr(qa_telemetry, 'enabled', lambda: True)
    status = {'policy': 'expired-disconnected', 'expired_removed': 2, 'shutdown_count': 2}
    qa_telemetry._write_diagnostic_record({'kind': 'resource', 'session_maintenance': status,
                                         'private-account': 'exclude-me'})
    record = json.loads(path.read_text())
    assert record['session_maintenance'] == status
    assert 'private-account' not in record and 'exclude-me' not in path.read_text()


def test_enabled_instrumentation_preserves_return_and_logs_bounded_state(monkeypatch):
    from types import SimpleNamespace
    from streamlit.runtime.scriptrunner.script_runner import ScriptRunner
    monkeypatch.setenv('RENDER_SERVICE_ID',qa_telemetry.QA_SERVICE)
    monkeypatch.setenv('SUPABASE_URL',qa_telemetry.QA_URL)
    monkeypatch.setattr(qa_telemetry,'_installed',False)
    monkeypatch.setattr(qa_telemetry,'_runs',0)
    monkeypatch.setattr(qa_telemetry,'_active',0)
    records=[]
    monkeypatch.setattr(qa_telemetry,'emit',lambda kind,**values: records.append((kind,values)))
    monkeypatch.setattr(qa_telemetry.threading,'Thread',lambda **kwargs: SimpleNamespace(start=lambda:None))
    monkeypatch.setattr(ScriptRunner,'_run_script',lambda self,data:'unchanged')
    # Keep the original method registered with monkeypatch for automatic cleanup.
    runner=SimpleNamespace(_session_id='private-session',_get_script_run_ctx=lambda:
        SimpleNamespace(session_state=SimpleNamespace(filtered_state={'private-secret':'do-not-log'})))
    qa_telemetry.install()
    assert ScriptRunner._run_script(runner,SimpleNamespace(fragment_id_queue=['x']))=='unchanged'
    assert qa_telemetry._active==0 and qa_telemetry._runs==1
    assert records[-1][1]['state_key_count']==1
    assert records[-1][1]['session']!='private-session'
    assert 'private-secret' not in str(records) and 'do-not-log' not in str(records)
