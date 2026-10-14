"""Isolated local UI test. No real accounts, rosters, or production datasets."""
from pathlib import Path
import sys
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dashboard.live_updates as updates

POINTER = ROOT / "reports/release-certification-20261009/browser-pointer.txt"
st.set_page_config(page_title="SDL refresh QA — test data only")
st.title("SDL refresh QA — test data only")
st.caption("Isolated timer/edit-protection test. No NFL data or real roster changes.")
st.session_state.setdefault("version", "v1")
st.session_state.setdefault("cc_selected_team", "Disposable QA team")
st.session_state.setdefault("auth_sentinel", "session-preserved")
st.write(f"Displayed version: {st.session_state.version}")
st.write(f"Selected team: {st.session_state.cc_selected_team}")
st.write(f"Session: {st.session_state.auth_sentinel}")
st.checkbox("Editing league settings", key="cc_team_settings_open")
if st.session_state.cc_team_settings_open:
    with st.form("qa_unsaved_form"):
        st.text_input("Unsaved league name", key="qa_draft")
        st.form_submit_button("Save test draft")


def pointer(_):
    return {"version": POINTER.read_text().strip(), "validation_status": "passed"}


def prepare(candidate):
    st.session_state.version = candidate["version"]


# Same production fragment and 60-second cadence; only the data source differs.
updates.publication_pointer = pointer
updates.watch_publication("isolated-fixture", st.session_state.version, True, prepare)
