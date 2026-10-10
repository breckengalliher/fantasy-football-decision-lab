"""Streamlit authentication UI backed by Supabase Auth."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import math
from uuid import uuid4

import streamlit as st
from streamlit_local_storage import LocalStorage

from dashboard.supabase_api import AuthSession, SupabaseAPI, SupabaseAPIError
from dashboard.auth_storage import AuthStorage, browser_auth_storage, PENDING_KEY, RECORD_KEY


SESSION_KEY = "command_center_auth_session"
RESTORE_KEY = "command_center_auth_restore_attempted"
STORAGE_KEY = "sdl_auth_refresh_token"
PERSISTENCE_KEY = "sdl_auth_persistence"
EXPIRY_KEY = "sdl_auth_persistence_expires_at"
PERSISTENCE_OPTIONS = {
    "This session only": "session",
    "Remember me for 30 days": "remember",
    "Keep me signed in": "always",
}


def _delete_if_present(storage: LocalStorage, item_key: str, *, component_key: str) -> None:
    """LocalStorage.deleteItem raises KeyError when its local mirror lacks a key."""
    try:
        storage.deleteItem(item_key, key=component_key)
    except KeyError:
        pass


def _save(session: AuthSession, storage: LocalStorage, persistence: str = "always") -> None:
    previous = current_session()
    if previous and previous.user_id != session.user_id:
        _clear_private_ui()
    st.session_state[SESSION_KEY] = asdict(session)
    st.session_state["command_center_persistence_mode"] = persistence
    if persistence == "session":
        _delete_if_present(storage, RECORD_KEY, component_key="clear_session_only_record")
        _delete_if_present(storage, STORAGE_KEY, component_key="clear_session_only_token")
        _delete_if_present(storage, PERSISTENCE_KEY, component_key="clear_session_only_mode")
        _delete_if_present(storage, EXPIRY_KEY, component_key="clear_session_only_expiry")
        return
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat() if persistence == 'remember' else None
    record = {'version': 2, 'revision': str(uuid4()), 'session': asdict(session), 'mode': persistence, 'expires_at': expiry}
    storage.setItem(RECORD_KEY, record)
    st.session_state['command_center_browser_record'] = record
    storage.setItem(STORAGE_KEY, session.refresh_token, key="persist_command_center_session")
    storage.setItem(PERSISTENCE_KEY, persistence, key="persist_command_center_mode")
    if persistence == "remember":
        storage.setItem(EXPIRY_KEY, expiry, key="persist_command_center_expiry")
    else:
        _delete_if_present(storage, EXPIRY_KEY, component_key="clear_command_center_expiry")


def persistence_expired(mode: str | None, expires_at: str | None, now: datetime | None = None) -> bool:
    if mode != "remember":
        return False
    if not expires_at:
        return True
    try:
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry <= (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def current_session() -> AuthSession | None:
    value = st.session_state.get(SESSION_KEY)
    if not isinstance(value, dict):
        return None
    try:
        return AuthSession(**value)
    except (TypeError, KeyError):
        return None


def access_refresh_due(session: AuthSession, now: datetime | None = None) -> bool:
    """Read expiry only to schedule refresh; never trust JWT claims for access.

    Supabase still verifies every token/refresh server-side. A malformed or
    missing expiry cannot justify returning a potentially stale credential.
    """
    try:
        payload = session.access_token.split('.')[1]
        decoded = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        expiry = decoded['exp']
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
            return True
    except (IndexError, KeyError, ValueError, TypeError, UnicodeError):
        return True
    return expiry <= (now or datetime.now(timezone.utc)).timestamp() + 60


def restore_session(api: SupabaseAPI, storage: LocalStorage) -> AuthSession | None:
    if isinstance(storage, AuthStorage):
        return _restore_coordinated(api, storage)
    if st.session_state.get("command_center_restore_retryable"):
        st.warning("Sign-in restoration is temporarily unavailable. Your remembered sign-in has been retained.")
        if st.button("Retry restoring sign-in", key="cc_retry_restore"):
            st.session_state.pop(RESTORE_KEY, None)
            st.session_state.pop("command_center_restore_retryable", None)
        else:
            return None
    existing = current_session()
    if existing and not access_refresh_due(existing):
        return existing
    if existing:
        # An open Streamlit session must rotate expired access credentials too,
        # not only a new tab restoring from browser storage. Preserve pending
        # edits on a transient outage but do not render private UI until retry.
        try:
            refreshed = api.refresh(existing.refresh_token)
            if refreshed.user_id != existing.user_id:
                raise SupabaseAPIError("The saved sign-in no longer matches this session.")
        except SupabaseAPIError as error:
            if error.retryable:
                st.session_state["command_center_restore_retryable"] = True
                st.rerun()
                return None
            _clear_private_session(storage)
            st.warning("Your sign-in has expired. Sign in again to access your saved teams.")
            return None
        _save(refreshed, storage, st.session_state.get("command_center_persistence_mode", "session"))
        return refreshed
    if st.session_state.get(RESTORE_KEY):
        return None
    refresh_token = storage.getItem(STORAGE_KEY)
    # The local-storage component may return before its browser value is ready;
    # mark the attempt only once it returns a concrete value.
    if refresh_token is None:
        return None
    st.session_state[RESTORE_KEY] = True
    if not refresh_token:
        return None
    persistence = storage.getItem(PERSISTENCE_KEY) or "always"
    expires_at = storage.getItem(EXPIRY_KEY)
    if persistence_expired(str(persistence), str(expires_at) if expires_at else None):
        _delete_if_present(storage, STORAGE_KEY, component_key="clear_expired_command_center_session")
        _delete_if_present(storage, PERSISTENCE_KEY, component_key="clear_expired_command_center_mode")
        _delete_if_present(storage, EXPIRY_KEY, component_key="clear_expired_command_center_expiry")
        return None
    try:
        session = api.refresh(str(refresh_token))
    except SupabaseAPIError as error:
        if error.retryable:
            # A timeout/outage does not revoke the user's remembered credential.
            # Retry only on an explicit user action, not on every Streamlit rerun.
            st.session_state["command_center_restore_retryable"] = True
            st.rerun()
            return None
        _delete_if_present(storage, STORAGE_KEY, component_key="clear_invalid_command_center_session")
        return None
    _save(session, storage, str(persistence))
    return session


def _clear_private_ui() -> None:
    for key in list(st.session_state):
        if str(key).startswith(("cc_", "command_center_")):
            st.session_state.pop(key, None)
    st.query_params.pop('team', None)


def _restore_coordinated(api, storage):
    """Never rotate a remembered token from a tab's stale Python state."""
    existing = current_session()
    if st.session_state.get('command_center_restore_retryable'):
        st.warning('Sign-in restoration is temporarily unavailable. Your saved sign-in and pending edits have been retained.')
        if not st.button('Retry restoring sign-in', key='cc_retry_restore'):
            return None
        st.session_state.pop('command_center_restore_retryable', None)
    record = storage.getItem(RECORD_KEY)
    mode = st.session_state.get('command_center_persistence_mode')
    if not storage.available:
        # No shared browser credential: explicitly degrade to visit-only mode.
        st.session_state['command_center_persistence_mode'] = 'session'
        mode = 'session'
    if existing and mode == 'session' and not record:
        if not access_refresh_due(existing):
            return existing
        try:
            refreshed = api.refresh(existing.refresh_token)
            if refreshed.user_id != existing.user_id:
                raise SupabaseAPIError('Session identity mismatch')
            st.session_state[SESSION_KEY] = asdict(refreshed)
            return refreshed
        except SupabaseAPIError as error:
            if error.retryable:
                st.session_state['command_center_restore_retryable'] = True
            else:
                _clear_private_ui()
            return None
    if isinstance(record, dict):
        if persistence_expired(record.get('mode'), record.get('expires_at')):
            storage.clear_session()
            _clear_private_ui()
            return None
        try:
            shared = AuthSession(**record['session'])
        except (KeyError, TypeError):
            shared = None
        if shared and not access_refresh_due(shared):
            if existing and shared == existing:
                st.session_state['command_center_browser_record'] = record
                return existing
            try:
                user = api.user(shared.access_token)
                if user.get('id') != shared.user_id:
                    raise SupabaseAPIError('Session identity mismatch')
            except SupabaseAPIError as error:
                if error.retryable:
                    st.session_state['command_center_restore_retryable'] = True
                else:
                    storage.clear_session()
                    _clear_private_ui()
                return None
            if existing and existing.user_id != shared.user_id:
                _clear_private_ui()
            st.session_state[SESSION_KEY] = asdict(shared)
            st.session_state['command_center_persistence_mode'] = record.get('mode', 'always')
            st.session_state['command_center_browser_record'] = record
            return shared
    result = storage.auth_result or {}
    if result.get('status') in {'rejected', 'expired'}:
        storage.clear_session()
        _clear_private_ui()
        return None
    if result.get('status') in {'retryable', 'unsupported'}:
        st.session_state['command_center_restore_retryable'] = True
        st.warning('Sign-in could not be restored safely. Retry, or sign in again. Your saved teams are unchanged.')
        return None
    if not record and not storage.getItem(STORAGE_KEY):
        if existing:
            _clear_private_ui()
        return None
    storage.refresh_session()
    return None


def _clear_private_session(storage) -> None:
    """Clear account-scoped UI and remembered credentials after invalidation."""
    st.session_state.pop(SESSION_KEY, None)
    st.session_state.pop(RESTORE_KEY, None)
    if isinstance(storage, AuthStorage):
        storage.clear_session()
    else:
        _delete_if_present(storage, STORAGE_KEY, component_key="clear_command_center_session")
        _delete_if_present(storage, PERSISTENCE_KEY, component_key="clear_command_center_mode")
        _delete_if_present(storage, EXPIRY_KEY, component_key="clear_command_center_expiry")
    _clear_private_ui()


def sign_out(api: SupabaseAPI, storage: LocalStorage | None = None) -> None:
    # render_auth already mounted the bridge. Queue deletion for its next run.
    storage = storage or AuthStorage({RECORD_KEY: st.session_state.get('command_center_browser_record'),
                                    STORAGE_KEY: current_session().refresh_token if current_session() else None})
    session = current_session()
    if session:
        try:
            api.sign_out(session.access_token)
        except SupabaseAPIError:
            pass
    _clear_private_session(storage)


def render_auth(api: SupabaseAPI, app_url: str) -> AuthSession | None:
    storage = browser_auth_storage(api)
    if storage is None:
        st.caption("Restoring your private session…")
        return None
    if st.session_state.pop("cc_clear_recovery_inputs", False):
        st.session_state.pop("cc_new_password", None)
        st.session_state.pop("cc_confirm_password", None)
    # A verified recovery session must reach the password form, not the roster.
    recovery = getattr(storage, "recovery", None)
    if isinstance(recovery, dict) and recovery.get("error"):
        st.session_state["cc_recovery_link_error"] = True
    if isinstance(recovery, dict) and recovery.get("type") in {"recovery", "invite"}:
        token = recovery.get("refresh_token")
        fingerprint = hashlib.sha256(str(token).encode()).hexdigest()
        if token and st.session_state.get("cc_recovery_link_seen") != fingerprint:
            st.session_state["cc_recovery_link_seen"] = fingerprint
            try:
                verified = api.refresh(str(token))
                st.session_state["cc_recovery_session"] = asdict(verified)
            except SupabaseAPIError:
                st.session_state["cc_recovery_link_error"] = True
    if st.session_state.get("cc_recovery_link_error"):
        st.warning("This account-access link could not be verified. Request a new recovery email.")
    if st.session_state.get("cc_recovery_session"):
        st.markdown("### Set your account password")
        st.caption("Use a unique password with at least 12 characters. Your saved rosters will not change.")
        with st.form("cc_set_recovery_password"):
            password = st.text_input("New password", type="password", key="cc_new_password")
            confirmation = st.text_input("Confirm new password", type="password", key="cc_confirm_password")
            persistence = st.selectbox("After updating password", list(PERSISTENCE_OPTIONS), index=0)
            submitted = st.form_submit_button("Save new password", type="primary")
        if submitted:
            if len(password) < 12:
                st.error("Use at least 12 characters.")
            elif password != confirmation:
                st.error("The passwords do not match.")
            else:
                recovered = AuthSession(**st.session_state["cc_recovery_session"])
                try:
                    api.update_password(recovered.access_token, password)
                    _save(recovered, storage, PERSISTENCE_OPTIONS[persistence])
                    st.session_state.pop("cc_recovery_session", None)
                    st.session_state.pop("cc_recovery_link_error", None)
                    st.session_state["cc_clear_recovery_inputs"] = True
                    st.rerun()
                except SupabaseAPIError as error:
                    st.error(str(error))
        return None
    session = restore_session(api, storage)
    # Recover a successful sign-in whose persistence write previously failed.
    # Honor the user's explicit choice; never persist session-only sign-ins.
    if st.session_state.get(PENDING_KEY):
        st.rerun()
    if session:
        # Non-privileged refresh rehearsal, only on the named isolated QA service.
        # No auth bypass, token changes, provider-setting changes or production UI.
        from dashboard.qa_telemetry import enabled as qa_enabled
        if qa_enabled() and api.url == 'https://deburhwrnuqeyexpezzo.supabase.co':
            with st.expander('QA session check'):
                st.caption('QA only: rehearse the same locked refresh path used before access expiry.')
                if st.button('QA: Rotate sign-in safely', key='cc_qa_rotate'):
                    storage.refresh_session(force=True)
                    st.rerun()
        return session

    st.markdown(
        '<section class="cc-auth-intro"><span>PRIVATE FANTASY DASHBOARD</span>'
        '<h2>Sign in to your Sunday Command Center</h2>'
        '<p>Save teams, monitor every starter, and see the lineup actions that matter before kickoff.</p></section>',
        unsafe_allow_html=True,
    )
    sign_in_tab, register_tab, recover_tab = st.tabs(["Sign in", "Create account", "Recover access"])
    with sign_in_tab:
        with st.form("command_center_sign_in"):
            email = st.text_input("Email", key="cc_login_email")
            password = st.text_input("Password", type="password", key="cc_login_password")
            persistence_label = st.selectbox(
                "Stay signed in",
                list(PERSISTENCE_OPTIONS),
                index=2,
                help="Use session only on shared devices. Keep me signed in lasts until you explicitly sign out or Supabase revokes the session.",
                key="cc_login_persistence",
            )
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            try:
                session = api.sign_in(email.strip(), password)
                _save(session, storage, PERSISTENCE_OPTIONS[persistence_label])
                st.rerun()
            except SupabaseAPIError as error:
                st.error(str(error))
    with register_tab:
        with st.form("command_center_register"):
            email = st.text_input("Email", key="cc_register_email")
            password = st.text_input("Create password", type="password", key="cc_register_password", help="Use at least 12 characters and a password you do not reuse elsewhere.")
            persistence_label = st.selectbox(
                "After account confirmation",
                list(PERSISTENCE_OPTIONS),
                index=2,
                help="Use session only on a shared device.",
                key="cc_register_persistence",
            )
            accepted = st.checkbox("I agree to store my account and fantasy roster data for this service.")
            submitted = st.form_submit_button("Create account", type="primary", width="stretch")
        if submitted:
            if len(password) < 12:
                st.error("Use a password with at least 12 characters.")
            elif not accepted:
                st.error("Confirm the data-storage notice before creating an account.")
            else:
                try:
                    payload = api.sign_up(email.strip(), password)
                    if payload.get("access_token"):
                        _save(api.session_from_payload(payload), storage, PERSISTENCE_OPTIONS[persistence_label])
                        st.rerun()
                    st.success("Check your email to confirm the account, then return here to sign in.")
                except SupabaseAPIError as error:
                    st.error(str(error))
    with recover_tab:
        with st.form("command_center_recovery"):
            email = st.text_input("Account email", key="cc_recovery_email")
            submitted = st.form_submit_button("Send recovery email", width="stretch")
        if submitted:
            try:
                api.recover(email.strip(), f"{app_url}?view=command-center&recovery=1")
            except SupabaseAPIError:
                pass
            st.success("If an account exists for that address, a recovery email will arrive shortly.")
    return None

