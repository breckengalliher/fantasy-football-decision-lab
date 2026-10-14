from dashboard import qa_browser_timing as timing


def test_recorder_requires_exact_isolated_service_database_and_local_flag(monkeypatch, tmp_path):
    flag = tmp_path / 'flag'
    monkeypatch.setattr(timing, 'FLAG', flag)
    monkeypatch.setenv('RENDER_SERVICE_ID', 'srv-db4ir249v7es7389sshg')
    monkeypatch.setenv('SUPABASE_URL', 'https://deburhwrnuqeyexpezzo.supabase.co')
    assert not timing.enabled()
    flag.touch()
    assert timing.enabled()
    monkeypatch.setenv('RENDER_SERVICE_ID', 'srv-db38uhom7kps73df3ogg')
    assert not timing.enabled()
    monkeypatch.setenv('RENDER_SERVICE_ID', 'srv-db4ir249v7es7389sshg')
    monkeypatch.setenv('SUPABASE_URL', 'https://vpcnkspovsfdlzzrtxjc.supabase.co')
    assert not timing.enabled()
