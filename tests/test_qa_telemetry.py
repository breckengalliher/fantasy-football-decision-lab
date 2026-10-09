from dashboard import qa_telemetry


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
