import pytest
import requests

from dashboard.supabase_api import SupabaseAPI, SupabaseAPIError


class Response:
    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status_code = status
        self.content = b"x" if payload is not None else b""

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError()
            error.response = self
            raise error

    def json(self):
        return self.payload


def test_sign_in_returns_session_without_exposing_service_role(monkeypatch):
    api = SupabaseAPI("https://project.supabase.co", "publishable")
    payload = {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600, "user": {"id": "user-1", "email": "fan@example.com"}}
    monkeypatch.setattr(api.http, "request", lambda *args, **kwargs: Response(payload))
    session = api.sign_in("fan@example.com", "password")
    assert session.user_id == "user-1"
    assert session.refresh_token == "refresh"


def test_auth_errors_are_sanitized(monkeypatch):
    api = SupabaseAPI("https://project.supabase.co", "publishable")
    monkeypatch.setattr(api.http, "request", lambda *args, **kwargs: Response({"message": "internal"}, 401))
    with pytest.raises(SupabaseAPIError, match="not accepted"):
        api.sign_in("fan@example.com", "wrong")


def test_unknown_table_is_rejected_before_request():
    api = SupabaseAPI("https://project.supabase.co", "publishable")
    with pytest.raises(ValueError, match="Unknown"):
        api.table("token", "private_secrets")


def test_signup_session_uses_public_conversion_method():
    api = SupabaseAPI("https://project.supabase.co", "publishable")
    session = api.session_from_payload(
        {"access_token": "access", "refresh_token": "refresh", "user": {"id": "user-2", "email": "new@example.com"}}
    )
    assert session.user_id == "user-2"

