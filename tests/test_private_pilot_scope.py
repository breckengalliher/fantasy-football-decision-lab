import pytest
from dashboard.pilot_scope import invited_accounts


def env():
    return {'SDL_RESTRICTED_PILOT':'1',
            'SDL_PILOT_ACCOUNT_IDS':','.join(f'00000000-0000-0000-0000-00000000000{i}' for i in range(4)),
            'SNAPSHOT_BASE_URL':'https://raw.githubusercontent.com/breckengalliher/sdl-release-qa-scheduler/qa-app-data/data/processed',
            'SUPABASE_URL':'https://deburhwrnuqeyexpezzo.supabase.co',
            'RENDER_SERVICE_ID':'srv-db4ir249v7es7389sshg'}


def test_private_pointer_requires_exact_qa_boundary():
    assert len(invited_accounts(env()))==4


@pytest.mark.parametrize('key,value',[
    ('SUPABASE_URL','https://production.supabase.co'),
    ('RENDER_SERVICE_ID','production'),
    ('RENDER_SERVICE_ID',''),
    ('SNAPSHOT_BASE_URL','https://raw.githubusercontent.com/breckengalliher/sdl-release-qa-scheduler/main/data/processed')])
def test_private_pointer_not_authorized_elsewhere(key,value):
    config=env(); config[key]=value
    with pytest.raises(ValueError,match='immutable'):
        invited_accounts(config)
