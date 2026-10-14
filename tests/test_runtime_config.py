from streamlit.errors import StreamlitSecretNotFoundError
from dashboard.runtime_config import account_config


class MissingSecrets:
    def get(self, *_args):
        raise StreamlitSecretNotFoundError("No secrets file")


def test_environment_only_accounts_do_not_require_secrets_file():
    assert account_config(MissingSecrets(), {"SUPABASE_URL": "https://qa.invalid", "SUPABASE_PUBLISHABLE_KEY": "public"}) == ("https://qa.invalid", "public")


def test_secrets_precedence_is_preserved():
    assert account_config({"SUPABASE_URL": "configured"}, {"SUPABASE_URL": "env", "SUPABASE_PUBLISHABLE_KEY": "public"}) == ("configured", "public")


def test_unconfigured_accounts_return_empty_values():
    assert account_config(MissingSecrets(), {}) == ("", "")
