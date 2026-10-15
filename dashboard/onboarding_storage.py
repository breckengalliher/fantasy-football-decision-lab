"""Recovery artifact's allowlisted, nonblocking native guide preference."""
import os
from pathlib import Path
import streamlit as st


def enabled(api):
    return bool(api and getattr(api, 'url', ''))


@st.cache_resource
def _component():
    source = (Path(__file__).parent / 'components' / 'onboarding.js').read_text(encoding='utf-8')
    return st.components.v2.component('sdl_onboarding_preference', js=source)


def load(*, dismiss=False):
    result = _component()(key='sdl_onboarding_native', data={'dismiss': bool(dismiss)},
                          default={'preference': None}, on_preference_change=lambda: None, height=1)
    value = result.preference
    if value is None or (dismiss and not value.get('write_ack')):
        # End this render; the browser acknowledgment schedules a fresh render.
        # Never block the server thread in a sleep loop while waiting for JS.
        st.stop()
    if not value.get('ok'):
        st.caption('Guide preference is available for this visit only; browser storage is unavailable.')
    return bool(value.get('dismissed'))
