"""Opt-in QA-only native UI timing, with visible, bounded local receipts.

Records no user identities, field values, tokens, URLs or network requests.
Disabled unless both isolated hosting/database identities and a local flag match.
"""
import json
import os
from pathlib import Path
import uuid

FLAG = Path('/tmp/sdl-qa-browser-timing')


def enabled():
    return (os.getenv('RENDER_SERVICE_ID') == 'srv-db4ir249v7es7389sshg'
            and os.getenv('SUPABASE_URL', '').rstrip('/') == 'https://deburhwrnuqeyexpezzo.supabase.co'
            and FLAG.is_file())


def render_completion(view):
    if not enabled():
        return
    import streamlit.components.v1 as components
    payload = dict(candidate=os.getenv('RENDER_GIT_COMMIT', ''), view=view, run=uuid.uuid4().hex)
    script = Path(__file__).with_name('qa_browser_timing.js').read_text(encoding='utf-8')
    components.html('<script>' + script + '\nparent.__sdlQaTiming.marker(' + json.dumps(payload) + ');</script>', height=0)
