"""Read optional Streamlit secrets without requiring a local secrets file."""
import os

from streamlit.errors import StreamlitSecretNotFoundError


def account_config(secrets, environ=None):
    environ = os.environ if environ is None else environ
    values = {}
    for name in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"):
        try:
            value = secrets.get(name, environ.get(name, ""))
        except StreamlitSecretNotFoundError:
            value = environ.get(name, "")
        values[name] = str(value)
    return values["SUPABASE_URL"], values["SUPABASE_PUBLISHABLE_KEY"]
