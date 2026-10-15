"""QA-only, allowlisted guide preference without a blocking legacy iframe."""
import os
from pathlib import Path
import streamlit as st


def enabled(api):
    return (os.getenv('RENDER_SERVICE_ID') == 'srv-db4ir249v7es7389sshg'
            and getattr(api, 'url', '').rstrip('/') == 'https://deburhwrnuqeyexpezzo.supabase.co')


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
