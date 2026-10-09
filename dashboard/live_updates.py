"""Lightweight publication polling, with conservative edit protection."""
import requests
import streamlit as st


def editing_roster(state) -> bool:
    if state.get("cc_team_settings_open"):
        return True
    return any((str(key).startswith("cc_manage_") and value is True)
               or (str(key).startswith(("cc_slot_pick_", "cc_compact_pick_")) and value is not None)
               for key, value in state.items())


def update_decision(current_version, candidate, *, command_center=False, state=None):
    if candidate.get("validation_status") != "passed" or not candidate.get("version"):
        return "unverified"
    if candidate["version"] == current_version:
        return "unchanged"
    if command_center and (not (state or {}).get("cc_selected_team") or editing_roster(state or {})):
        return "defer"
    return "apply"


@st.cache_data(ttl=30, max_entries=1, show_spinner=False)
def publication_pointer(base_url):
    response = requests.get(f"{base_url}/publication_manifest.json", timeout=(2, 4))
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    return response.json()


@st.fragment(run_every="60s")
def watch_publication(base_url, current_version, command_center, prepare_update):
    """Poll only the small pointer; load assets only on a new version.

    A full rerun happens once per changed, preloaded version, not per timer tick.
    Open settings, management controls, or staged player selections defer it.
    """
    try:
        candidate = publication_pointer(base_url)
        decision = update_decision(current_version, candidate, command_center=command_center, state=st.session_state)
        if decision == "defer":
            st.info("New validated data is available. Finish or close your roster edits; they have not been changed.")
        elif decision == "apply":
            prepare_update(candidate)
            st.rerun()
        elif decision == "unverified":
            st.caption("Automatic update verification awaits a versioned publication. Check official availability before kickoff.")
    except (requests.RequestException, ValueError, KeyError, OSError):
        # Keep the previously drawn UI; never replace its timestamp on failure.
        st.caption("Update check unavailable. Displayed data has not been refreshed; check its timestamp.")
