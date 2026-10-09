"""Streamlit authentication UI backed by Supabase Auth."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib

import streamlit as st
from streamlit_local_storage import LocalStorage

from dashboard.supabase_api import AuthSession, SupabaseAPI, SupabaseAPIError
from dashboard.auth_storage import AuthStorage, browser_auth_storage, PENDING_KEY


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
    st.session_state[SESSION_KEY] = asdict(session)
    st.session_state["command_center_persistence_mode"] = persistence
    if persistence == "session":
        _delete_if_present(storage, STORAGE_KEY, component_key="clear_session_only_token")
        _delete_if_present(storage, PERSISTENCE_KEY, component_key="clear_session_only_mode")
        _delete_if_present(storage, EXPIRY_KEY, component_key="clear_session_only_expiry")
        return
    storage.setItem(STORAGE_KEY, session.refresh_token, key="persist_command_center_session")
    storage.setItem(PERSISTENCE_KEY, persistence, key="persist_command_center_mode")
    if persistence == "remember":
        expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
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


def restore_session(api: SupabaseAPI, storage: LocalStorage) -> AuthSession | None:
    existing = current_session()
    if existing:
        return existing
    if st.session_state.get("command_center_restore_retryable"):
        st.warning("Sign-in restoration is temporarily unavailable. Your remembered sign-in has been retained.")
        if st.button("Retry restoring sign-in", key="cc_retry_restore"):
            st.session_state.pop(RESTORE_KEY, None)
            st.session_state.pop("command_center_restore_retryable", None)
        else:
            return None
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


def sign_out(api: SupabaseAPI, storage: LocalStorage | None = None) -> None:
    # render_auth already mounted the bridge. Queue deletion for its next run.
    storage = AuthStorage({})
    session = current_session()
    if session:
        try:
            api.sign_out(session.access_token)
        except SupabaseAPIError:
            pass
    st.session_state.pop(SESSION_KEY, None)
    st.session_state.pop(RESTORE_KEY, None)
    _delete_if_present(storage, STORAGE_KEY, component_key="clear_command_center_session")
    _delete_if_present(storage, PERSISTENCE_KEY, component_key="clear_command_center_mode")
    _delete_if_present(storage, EXPIRY_KEY, component_key="clear_command_center_expiry")
    for key in list(st.session_state):
        if str(key).startswith(("cc_", "command_center_")):
            st.session_state.pop(key, None)
    st.query_params.pop("team", None)


def render_auth(api: SupabaseAPI, app_url: str) -> AuthSession | None:
    storage = browser_auth_storage()
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
    selected_mode = st.session_state.get("command_center_persistence_mode") or PERSISTENCE_OPTIONS.get(st.session_state.get("cc_login_persistence"))
    if session and storage.available and not storage.getItem(STORAGE_KEY) and selected_mode in {"always", "remember"}:
        _save(session, storage, selected_mode)
    if st.session_state.get(PENDING_KEY):
        st.rerun()
    if session:
        if storage.available and not storage.getItem(STORAGE_KEY) and selected_mode is None:
            if st.button("Remember this sign-in", help="Keep this existing sign-in on this device until you sign out. Do not use on a shared device."):
                _save(session, storage, "always")
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

