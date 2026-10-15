"""Server-controlled rollout of the reviewed native browser components.

This selects rendering transport only. It does not choose a database, accept a
client-side flag, bypass authentication, or change the session protocol.
"""
import os


def native_enabled(api, environ=None):
    environ = os.environ if environ is None else environ
    mode = environ.get('SDL_BROWSER_COMPONENT_TRANSPORT', 'auto').strip().lower()
    if mode not in {'auto', 'native', 'legacy'}:
        raise ValueError('SDL_BROWSER_COMPONENT_TRANSPORT must be auto, native, or legacy')
    if mode == 'native':
        return bool(api and getattr(api, 'url', ''))
    if mode == 'legacy':
        return False
    # Preserve the already-certified QA default. Other deployments require an
    # explicit, separately approved server configuration change to opt in.
    return (environ.get('RENDER_SERVICE_ID') == 'srv-db4ir249v7es7389sshg'
            and getattr(api, 'url', '').rstrip('/') == 'https://deburhwrnuqeyexpezzo.supabase.co')
