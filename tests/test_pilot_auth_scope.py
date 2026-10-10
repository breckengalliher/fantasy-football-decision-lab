"""The restricted pilot offers existing-account sign-in, never account setup."""
from contextlib import nullcontext
from types import SimpleNamespace
from pathlib import Path

import pytest

from dashboard import auth_ui
from dashboard.pilot_scope import invited_accounts, account_allowed

FIRST = '11111111-1111-4111-8111-111111111111'
SECOND = '22222222-2222-4222-8222-222222222222'
THIRD = '33333333-3333-4333-8333-333333333333'
FOURTH = '44444444-4444-4444-8444-444444444444'
FIFTH = '55555555-5555-4555-8555-555555555555'
INVITES = ','.join((FIRST, SECOND, THIRD, FOURTH, FIFTH))
PIN = 'https://raw.githubusercontent.com/breckengalliher/fantasy-football-decision-lab/' + 'a' * 40 + '/data/processed'


class Screen:
    def __init__(self, state=None):
        self.session_state = state or {}
        self.offered_tabs = None
        self.forms = []

    def tabs(self, labels):
        self.offered_tabs = labels
        return [nullcontext() for _ in labels]

    def form(self, name):
        self.forms.append(name)
        return nullcontext()

    def text_input(self, *args, **kwargs):
        return ''

    def selectbox(self, label, choices, **kwargs):
        return choices[0]

    def form_submit_button(self, *args, **kwargs):
        return False

    def markdown(self, *args, **kwargs):
        pass

    caption = warning = markdown


def setup(monkeypatch, *, recovery=None, state=None, session=None):
    monkeypatch.setenv('SDL_PILOT_PREPROVISIONED_ONLY', '1')
    screen = Screen(state)
    monkeypatch.setattr(auth_ui, 'st', screen)
    monkeypatch.setattr(auth_ui, 'browser_auth_storage', lambda api: SimpleNamespace(recovery=recovery))
    monkeypatch.setattr(auth_ui, 'restore_session', lambda api, storage: session)
    # Any authentication/provider mutation would fail, including recovery refresh.
    return screen, SimpleNamespace()


def test_pilot_offers_only_sign_in(monkeypatch):
    screen, api = setup(monkeypatch)
    assert auth_ui.render_auth(api, 'https://qa.example/') is None
    assert screen.offered_tabs == ['Sign in']
    assert screen.forms == ['command_center_sign_in']


@pytest.mark.parametrize('recovery', [
    {'type': 'recovery', 'refresh_token': 'test-only'},
    {'type': 'invite', 'refresh_token': 'test-only'},
    {'error': 'invalid-link'},
])
def test_pilot_recovery_link_never_reaches_provider_or_password_form(monkeypatch, recovery):
    screen, api = setup(monkeypatch, recovery=recovery)
    assert auth_ui.render_auth(api, 'https://qa.example/') is None
    assert screen.forms == []


def test_pilot_blocks_already_pending_password_submission(monkeypatch):
    screen, api = setup(monkeypatch, state={'cc_recovery_session': {'access_token': 'test-only'}})
    assert auth_ui.render_auth(api, 'https://qa.example/') is None
    assert screen.forms == []


def test_existing_pilot_session_remains_usable(monkeypatch):
    session = object()
    screen, api = setup(monkeypatch, session=session)
    # The QA-only refresh rehearsal remains off for this mocked provider.
    api.url = 'https://pilot.example'
    monkeypatch.setattr('dashboard.qa_telemetry.enabled', lambda: False)
    assert auth_ui.render_auth(api, 'https://qa.example/') is session
    assert screen.forms == []


def test_invited_scope_fails_closed_for_missing_duplicate_or_unpinned_config():
    env = {'SDL_RESTRICTED_PILOT': '1', 'SDL_PILOT_ACCOUNT_IDS': INVITES,
           'SNAPSHOT_BASE_URL': PIN}
    accounts = invited_accounts(env)
    assert account_allowed(FIRST, accounts) and account_allowed(SECOND, accounts)
    assert all(account_allowed(value, accounts) for value in (FIRST, SECOND, THIRD, FOURTH, FIFTH))
    assert not account_allowed('66666666-6666-4666-8666-666666666666', accounts)
    assert invited_accounts({}) is None
    for broken in ({**env, 'SDL_PILOT_ACCOUNT_IDS': ''},
                   {**env, 'SDL_PILOT_ACCOUNT_IDS': ','.join((FIRST, SECOND, THIRD, FOURTH, FIRST))},
                   {**env, 'SDL_PILOT_ACCOUNT_IDS': ','.join((FIRST, SECOND))},
                   {**env, 'SDL_PILOT_ACCOUNT_IDS': INVITES + ',66666666-6666-4666-8666-666666666666'},
                   {**env, 'SNAPSHOT_BASE_URL': PIN.replace('a' * 40, 'main')}):
        with pytest.raises(ValueError):
            invited_accounts(broken)


def test_four_launch_invitees_exclude_fifth_capacity_tester():
    env = {'SDL_RESTRICTED_PILOT': '1',
           'SDL_PILOT_ACCOUNT_IDS': ','.join((FIRST, SECOND, THIRD, FOURTH)),
           'SNAPSHOT_BASE_URL': PIN}
    accounts = invited_accounts(env)
    assert all(account_allowed(value, accounts) for value in (FIRST, SECOND, THIRD, FOURTH))
    assert not account_allowed(FIFTH, accounts)
    for invalid in (','.join((FIRST, SECOND, THIRD)),
                    ','.join((FIRST, SECOND, THIRD, FIRST)),
                    ','.join((FIRST, SECOND, THIRD, 'null'))):
        with pytest.raises(ValueError):
            invited_accounts({**env, 'SDL_PILOT_ACCOUNT_IDS': invalid})


def test_uninvited_restored_account_clears_private_state_before_access(monkeypatch):
    screen, api = setup(monkeypatch, session=SimpleNamespace(user_id='uninvited'))
    monkeypatch.setenv('SDL_RESTRICTED_PILOT', '1')
    monkeypatch.setenv('SDL_PILOT_ACCOUNT_IDS', INVITES)
    monkeypatch.setenv('SNAPSHOT_BASE_URL', PIN)
    cleared = []
    monkeypatch.setattr(auth_ui, '_clear_private_session', lambda storage: cleared.append(True))
    assert auth_ui.render_auth(api, 'https://qa.example/') is None
    assert cleared == [True] and screen.forms == ['command_center_sign_in']


def test_uninvited_remembered_session_dispatches_clear_before_restore(monkeypatch):
    screen, api = setup(monkeypatch, session=SimpleNamespace(user_id='uninvited'))
    monkeypatch.setenv('SDL_RESTRICTED_PILOT', '1')
    monkeypatch.setenv('SDL_PILOT_ACCOUNT_IDS', INVITES)
    monkeypatch.setenv('SNAPSHOT_BASE_URL', PIN)
    def queue_clear(storage):
        screen.session_state[auth_ui.PENDING_KEY] = {'clear': True}
    monkeypatch.setattr(auth_ui, '_clear_private_session', queue_clear)
    def rerun():
        raise RuntimeError('dispatch pending browser clear')
    screen.rerun = rerun
    with pytest.raises(RuntimeError, match='dispatch pending browser clear'):
        auth_ui.render_auth(api, 'https://qa.example/')
    assert screen.session_state[auth_ui.PENDING_KEY]['clear'] is True
    assert screen.forms == []


def test_mobile_pilot_navigation_does_not_offer_excluded_routes(monkeypatch):
    from dashboard import product_experience
    monkeypatch.setenv('SDL_RESTRICTED_PILOT', '1')
    output = []
    monkeypatch.setattr(product_experience, 'st', SimpleNamespace(
        query_params={}, markdown=lambda value, **kwargs: output.append(value)))
    product_experience.mobile_navigation()
    assert 'command-center' in output[0] and 'decision-room' in output[0]
    assert 'player-trends' in output[0] and 'how-it-works' not in output[0]


def test_uninvited_successful_login_is_not_persisted(monkeypatch):
    screen, api = setup(monkeypatch)
    monkeypatch.setenv('SDL_RESTRICTED_PILOT', '1')
    monkeypatch.setenv('SDL_PILOT_ACCOUNT_IDS', INVITES)
    monkeypatch.setenv('SNAPSHOT_BASE_URL', PIN)
    screen.form_submit_button = lambda *args, **kwargs: True
    revoked, cleared = [], []
    api.sign_in = lambda *args: SimpleNamespace(user_id='uninvited', access_token='test-only')
    api.sign_out = lambda token: revoked.append(token)
    monkeypatch.setattr(auth_ui, '_clear_private_session', lambda storage: cleared.append(True))
    monkeypatch.setattr(auth_ui, '_save', lambda *args: pytest.fail('uninvited session persisted'))
    assert auth_ui.render_auth(api, 'https://qa.example/') is None
    assert revoked == ['test-only'] and cleared == [True]


def test_pilot_team_setup_cannot_reach_creation_or_import(monkeypatch):
    from dashboard import command_center_v2
    monkeypatch.setenv('SDL_RESTRICTED_PILOT', '1')
    output = []
    monkeypatch.setattr(command_center_v2, 'st', SimpleNamespace(caption=output.append))
    # An empty repo cannot create, configure or import anything.
    command_center_v2._team_setup(SimpleNamespace(), 2026, None)
    assert output == ['Teams are provided for this pilot. Use your existing fantasy team.']


@pytest.mark.parametrize('route', ['decision-room', 'player-trends', 'how-it-works', 'home'])
def test_restricted_direct_route_cannot_render_public_model_before_login(monkeypatch, route):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('SDL_RESTRICTED_PILOT', '1')
    monkeypatch.setenv('SDL_PILOT_ACCOUNT_IDS', INVITES)
    monkeypatch.setenv('SNAPSHOT_BASE_URL', PIN)
    monkeypatch.setenv('SUPABASE_URL', 'https://qa.example')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'test-only')
    monkeypatch.setattr(auth_ui, 'browser_auth_storage', lambda api: None)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'dashboard/app.py', default_timeout=30)
    app.query_params['view'] = route
    app.run()
    assert not app.exception
    assert app.sidebar.radio[0].options == ['Sunday Command Center', 'Decision Room', 'Player Trends']
    assert not app.dataframe
    assert any('Restoring your private session' in item.value for item in app.caption)
    if route not in ('decision-room', 'player-trends'):
        assert app.query_params['view'] == 'command-center'


def test_pilot_excludes_sleeper_sync_without_reading_or_changing_saved_roster(monkeypatch):
    from dashboard import command_center_v2
    monkeypatch.setenv("SDL_RESTRICTED_PILOT", "1")
    # No repository or provider operation is available in the pilot.
    command_center_v2._sleeper_sync_panel({"id": "disposable-test-only"}, object(), [], None)
