from types import SimpleNamespace
import pytest
from dashboard.publication_client import publication_get, QA_REPOSITORY

URL = f'https://raw.githubusercontent.com/{QA_REPOSITORY}/qa-app-data/data/processed/publication_manifest.json'

class Session:
    def __init__(self, status=200): self.calls=[]; self.status=status
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return SimpleNamespace(status_code=self.status)

@pytest.fixture
def qa(monkeypatch):
    monkeypatch.setenv('RENDER_SERVICE_ID','srv-db4ir249v7es7389sshg')
    monkeypatch.setenv('SUPABASE_URL','https://deburhwrnuqeyexpezzo.supabase.co')
    monkeypatch.setenv('QA_SNAPSHOT_READER_TOKEN','test-only-token')

def test_scoped_private_request(qa):
    session=Session(); publication_get(session,URL,(2,4))
    url, args=session.calls[0]
    assert url.startswith(f'https://api.github.com/repos/{QA_REPOSITORY}/contents/')
    assert args['allow_redirects'] is False
    assert args['headers']['Authorization']=='Bearer test-only-token'

def test_public_read_never_gets_credential(qa):
    session=Session(); publication_get(session,'https://raw.githubusercontent.com/owner/repo/main/data/processed/file',(2,4))
    assert 'headers' not in session.calls[0][1]

@pytest.mark.parametrize('variable,value',[('RENDER_SERVICE_ID','production'),('SUPABASE_URL','https://production.supabase.co'),('QA_SNAPSHOT_READER_TOKEN','')])
def test_missing_or_wrong_scope_fails_closed(qa,monkeypatch,variable,value):
    monkeypatch.setenv(variable,value); session=Session()
    with pytest.raises(ValueError): publication_get(session,URL,(2,4))
    assert not session.calls

@pytest.mark.parametrize('status',[301,302,307,404])
def test_redirect_and_missing_private_data_do_not_fallback(qa,status):
    with pytest.raises(ValueError): publication_get(Session(status),URL,(2,4))

@pytest.mark.parametrize('url',[URL.replace('https:','http:'),URL.replace('qa-app-data','main'),URL.replace('publication_manifest.json','secrets.toml')])
def test_invalid_private_path_no_network(qa,url):
    session=Session()
    with pytest.raises(ValueError): publication_get(session,url,(2,4))
    assert not session.calls
