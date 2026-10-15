"""Actual Streamlit forms with fake provider/storage; no account operations."""
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from dashboard import auth_storage, auth_ui


FIRST = "11111111-1111-4111-8111-111111111111"
ACCOUNTS = ",".join(f"{i}" * 8 + "-" + f"{i}" * 4 + "-4" + f"{i}" * 3 + "-8" + f"{i}" * 3 + "-" + f"{i}" * 12 for i in range(1, 5))
PIN = "https://raw.githubusercontent.com/breckengalliher/fantasy-football-decision-lab/" + "a" * 40 + "/data/processed"

SCRIPT = '''
import streamlit as st
from dashboard.auth_ui import render_auth
from dashboard.supabase_api import AuthSession, SupabaseAPIError
class FakeAPI:
    url = 'https://fixture.example.invalid'
    def refresh(self, token):
        if st.session_state.get('test_invalid_link'):
            raise SupabaseAPIError('Account link could not be verified')
        return AuthSession('fixture-access', 'fixture-refresh', 3600,
                           '11111111-1111-4111-8111-111111111111', 'fixture@example.invalid')
    def sign_in(self, email, password):
        st.session_state['test_signin_length'] = len(password)
        raise SupabaseAPIError('The email or password was not accepted.')
    def update_password(self, token, password):
        if st.session_state.get('test_password_error'):
            raise SupabaseAPIError(st.session_state['test_password_error'])
        st.session_state['test_update_length'] = len(password)
    def recover(self, email, redirect):
        st.session_state['test_recovery_request_count'] = st.session_state.get('test_recovery_request_count', 0) + 1
        outcome = st.session_state.get('test_recovery_outcome', 'accepted')
        if outcome != 'accepted':
            raise SupabaseAPIError('fixture provider error', retryable=outcome == 'retryable')
session = render_auth(FakeAPI(), 'https://fixture.example.invalid')
if session:
    st.session_state['test_private_view_reached'] = True
'''


@pytest.fixture
def screen(monkeypatch):
    def make(*, mode="pilot", recovery=None, invalid=False):
        monkeypatch.setenv("SDL_RESTRICTED_PILOT", "0" if mode == "public" else "1")
        monkeypatch.setenv("SDL_PILOT_PREPROVISIONED_ONLY", "1" if mode == "managed" else "0")
        monkeypatch.setenv("SDL_PILOT_ACCOUNT_IDS", ACCOUNTS)
        monkeypatch.setenv("SNAPSHOT_BASE_URL", PIN)
        monkeypatch.setattr(auth_ui, "browser_auth_storage", lambda *_: auth_storage.AuthStorage(
            {}, recovery=auth_ui.st.session_state.get("test_recovery")))
        monkeypatch.setattr(auth_ui, "restore_session", lambda *_: None)
        monkeypatch.setattr(auth_ui, "_save", lambda *_: auth_ui.st.session_state.__setitem__("test_saved_session", True))
        app = AppTest.from_string(SCRIPT, default_timeout=20)
        app.session_state["test_recovery"] = recovery
        app.session_state["test_invalid_link"] = invalid
        app.session_state["cc_selected_team"] = "fixture-existing-team"
        app.session_state["cc_target_slot"] = "fixture-unsaved-choice"
        app.run()
        assert not app.exception
        return app
    return make


def all_text(app):
    return "\n".join(item.value for collection in (app.info, app.caption, app.warning, app.error, app.success) for item in collection)


def test_pilot_setup_login_and_recovery_help_match_available_controls(screen):
    app = screen()
    text = all_text(app)
    assert "newest invitation email" in text and "at least 12 characters" in text
    assert "set one with the pilot organizer" in text
    assert "does not create a new password" in text
    assert "Forgot your password" in text and "spam folder" in text
    assert "pilot organizer" in text and "Keep passwords and links private" in text
    assert [tab.label for tab in app.tabs] == ["Sign in", "Recover access"]
    assert [button.label for button in app.button] == ["Sign in", "Send recovery email"]


def test_managed_pilot_has_organizer_path_without_offering_self_service(screen):
    app = screen(mode="managed")
    assert "provided sign-in account" in all_text(app)
    assert "forgot your password" in all_text(app)
    assert not app.info
    assert [button.label for button in app.button] == ["Sign in"]


def test_existing_short_password_is_still_submitted_to_signin(screen):
    app = screen()
    app.text_input(key="cc_login_email").set_value("fixture@example.invalid")
    app.text_input(key="cc_login_password").set_value("short")
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["test_signin_length"] == 5
    assert [error.value for error in app.error] == ["The email or password was not accepted."]
    assert "test_update_length" not in app.session_state


@pytest.mark.parametrize("mode", ["pilot", "public"])
@pytest.mark.parametrize("kind", ["invite", "recovery", "error"])
def test_unverified_link_gives_reachable_next_step_and_no_password_form(screen, mode, kind):
    recovery = {"error": "fixture-error"} if kind == "error" else {"type": kind, "refresh_token": "fixture-expired"}
    app = screen(mode=mode, recovery=recovery, invalid=True)
    warning = "\n".join(item.value for item in app.warning)
    assert "could not be verified" in warning and "may have expired" in warning
    assert "Recover access tab" in warning
    assert "cc_set_recovery_password" not in [form.key for form in app.get("form")]
    assert "cc_recovery_session" not in app.session_state
    assert "test_private_view_reached" not in app.session_state


@pytest.mark.parametrize("kind", ["invite", "recovery"])
@pytest.mark.parametrize("length", [11, 12])
def test_verified_password_form_enforces_creation_length_without_changing_drafts(screen, kind, length):
    app = screen(recovery={"type": kind, "refresh_token": "fixture-link"})
    assert [field.label for field in app.text_input] == ["New password", "Confirm new password"]
    assert "at least 12 characters" in all_text(app)
    assert "test_private_view_reached" not in app.session_state
    value = "x" * length
    app.text_input[0].set_value(value)
    app.text_input[1].set_value(value)
    app.button[0].click().run()
    assert not app.exception
    if length < 12:
        assert "test_update_length" not in app.session_state
        assert any("at least 12" in error.value for error in app.error)
    else:
        assert app.session_state["test_update_length"] == 12
        assert "cc_recovery_session" not in app.session_state
        assert "cc_new_password" not in app.session_state and "cc_confirm_password" not in app.session_state
    assert app.session_state["cc_selected_team"] == "fixture-existing-team"
    assert app.session_state["cc_target_slot"] == "fixture-unsaved-choice"


def test_mismatched_confirmation_does_not_call_password_update(screen):
    app = screen(recovery={"type": "recovery", "refresh_token": "fixture-link"})
    app.text_input[0].set_value("fixture-long-password")
    app.text_input[1].set_value("different-long-password")
    app.button[0].click().run()
    assert not app.exception
    assert any("do not match" in error.value for error in app.error)
    assert "test_update_length" not in app.session_state


@pytest.mark.parametrize("message", [
    "Choose a new password different from your current password.",
    "The new password was not accepted. Choose a different, strong password.",
    "The account service is temporarily unavailable.",
])
def test_password_rejection_keeps_setup_and_next_steps_visible(screen, message):
    app = screen(recovery={"type": "recovery", "refresh_token": "fixture-link"})
    app.session_state["test_password_error"] = message
    app.text_input[0].set_value("fixture-long-password")
    app.text_input[1].set_value("fixture-long-password")
    app.button[0].click().run()
    assert not app.exception
    assert [error.value for error in app.error] == [message]
    assert "at least 12 characters" in all_text(app)
    assert [field.label for field in app.text_input] == ["New password", "Confirm new password"]
    assert "test_update_length" not in app.session_state
    assert "test_private_view_reached" not in app.session_state


def test_fresh_verified_link_clears_obsolete_link_warning(screen):
    app = screen(recovery={"type": "recovery", "refresh_token": "fixture-old"}, invalid=True)
    assert app.warning
    app.session_state["test_recovery"] = {"type": "recovery", "refresh_token": "fixture-new"}
    app.session_state["test_invalid_link"] = False
    app.run()
    assert not app.exception
    assert not app.warning
    assert [field.label for field in app.text_input] == ["New password", "Confirm new password"]


@pytest.mark.parametrize("outcome", ["accepted", "nonretryable", "retryable"])
def test_public_recovery_uses_neutral_response_and_truthful_outage_message(screen, outcome):
    app = screen(mode="public")
    app.session_state["test_recovery_outcome"] = outcome
    app.text_input(key="cc_recovery_email").set_value("fixture@example.invalid")
    next(button for button in app.button if button.label == "Send recovery email").click().run()
    assert not app.exception
    assert app.session_state["test_recovery_request_count"] == 1
    responses = [item.value for item in app.info if item.value.startswith("If an account exists")]
    assert len(responses) == 1
    assert "Delivery is not confirmed" in responses[0]
    assert not app.success
    assert "fixture provider error" not in all_text(app)


def test_confirmed_session_returns_without_setup_prompts_or_private_state_changes(monkeypatch, screen):
    app = screen()
    session = SimpleNamespace(user_id=FIRST, access_token="fixture-only")
    monkeypatch.setattr(auth_ui, "restore_session", lambda *_: session)
    monkeypatch.setattr("dashboard.qa_telemetry.enabled", lambda: False)
    app.run()
    assert not app.exception
    assert not app.text_input and not app.info and not app.warning
    assert app.session_state["test_private_view_reached"] is True
    assert app.session_state["cc_target_slot"] == "fixture-unsaved-choice"


@pytest.mark.parametrize('mode', ['pilot', 'public'])
def test_recovery_responses_do_not_enumerate_accounts_or_pilot_access(screen, mode):
    responses = []
    for address, outcome in [('known@example.invalid', 'accepted'),
                             ('unknown@example.invalid', 'nonretryable'),
                             ('outside-pilot@example.invalid', 'retryable')]:
        app = screen(mode=mode)
        app.session_state['test_recovery_outcome'] = outcome
        app.text_input(key='cc_recovery_email').set_value(address)
        next(b for b in app.button if b.label == 'Send recovery email').click().run()
        assert not app.exception
        responses.append([v.value for v in app.info if v.value.startswith('If an account exists')])
        assert not app.error and not app.success
        assert all(tab.label != 'Create account' for tab in app.tabs) if mode == 'pilot' else True
    assert responses[0] == responses[1] == responses[2]


def test_success_confirmation_reaches_authenticated_view_without_roster_changes(monkeypatch, screen):
    app = screen()
    app.session_state['cc_password_updated'] = True
    session = SimpleNamespace(user_id=FIRST, access_token='fixture-only')
    monkeypatch.setattr(auth_ui, 'restore_session', lambda *_: session)
    monkeypatch.setattr('dashboard.qa_telemetry.enabled', lambda: False)
    app.run()
    assert not app.exception
    assert app.session_state['test_private_view_reached'] is True
    assert any('Your password was saved' in item.value for item in app.success)
    assert app.session_state['cc_target_slot'] == 'fixture-unsaved-choice'
