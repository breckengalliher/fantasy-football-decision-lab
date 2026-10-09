import pytest
import requests

from dashboard.supabase_api import SupabaseAPI, SupabaseAPIError


@pytest.mark.parametrize("body,expected", [
    ('{"code":"same_password","message":"private provider details"}', "different from your current"),
    ('{"code":"weak_password"}', "different, strong password"),
    ('not json', "different, strong password"),
    ('[]', "different, strong password"),
])
def test_password_validation_is_not_reported_as_service_outage(monkeypatch, body, expected):
    response = requests.Response()
    response.status_code = 422
    response._content = body.encode()
    api = SupabaseAPI("https://qa.example", "publishable")
    monkeypatch.setattr(api.http, "request", lambda *args, **kwargs: response)
    with pytest.raises(SupabaseAPIError) as caught:
        api.update_password("test-user-token", "test-password-long")
    assert expected in str(caught.value)
    assert not caught.value.retryable
    assert "private provider details" not in str(caught.value)
    assert "temporarily unavailable" not in str(caught.value)
