"""Small Supabase Auth/PostgREST client for the Sunday Command Center.

The publishable key is safe to ship to a browser. The secret/service key is
intentionally unsupported here so normal application code cannot bypass RLS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class SupabaseAPIError(RuntimeError):
    """A sanitized provider failure safe to show in application UI."""


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    email: str


class SupabaseAPI:
    def __init__(self, url: str, publishable_key: str, timeout: tuple[float, float] = (3.05, 10)) -> None:
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key
        self.timeout = timeout
        self.http = requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.url and self.publishable_key)

    def _headers(self, access_token: str | None = None, *, prefer: str | None = None) -> dict[str, str]:
        headers = {"apikey": self.publishable_key, "Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(self, method: str, path: str, *, access_token: str | None = None, **kwargs: Any) -> Any:
        try:
            response = self.http.request(
                method, f"{self.url}{path}", headers=self._headers(access_token, prefer=kwargs.pop("prefer", None)),
                timeout=self.timeout, **kwargs,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            status = getattr(error.response, "status_code", None)
            if status in {400, 401} and path.startswith("/auth/"):
                raise SupabaseAPIError("The email or password was not accepted.") from None
            if status in {400, 403, 409} and path.startswith("/rest/"):
                raise SupabaseAPIError("The roster could not be saved. Reload it and verify position eligibility; another visit may have changed it.") from None
            if status == 429:
                raise SupabaseAPIError("Too many attempts. Please wait before trying again.") from None
            raise SupabaseAPIError("The account service is temporarily unavailable.") from None
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _session(payload: dict[str, Any]) -> AuthSession:
        user = payload.get("user") or {}
        return AuthSession(
            access_token=str(payload["access_token"]), refresh_token=str(payload["refresh_token"]),
            expires_in=int(payload.get("expires_in", 3600)), user_id=str(user["id"]), email=str(user.get("email", "")),
        )

    def session_from_payload(self, payload: dict[str, Any]) -> AuthSession:
        """Build a validated session from a successful Auth response."""
        return self._session(payload)

    def sign_up(self, email: str, password: str) -> dict[str, Any]:
        return self._request("POST", "/auth/v1/signup", json={"email": email, "password": password})

    def sign_in(self, email: str, password: str) -> AuthSession:
        return self._session(self._request("POST", "/auth/v1/token?grant_type=password", json={"email": email, "password": password}))

    def refresh(self, refresh_token: str) -> AuthSession:
        return self._session(self._request("POST", "/auth/v1/token?grant_type=refresh_token", json={"refresh_token": refresh_token}))

    def recover(self, email: str, redirect_to: str) -> None:
        # Always return the same UI response so callers cannot enumerate users.
        self._request("POST", "/auth/v1/recover", json={"email": email, "redirect_to": redirect_to})

    def sign_out(self, access_token: str) -> None:
        self._request("POST", "/auth/v1/logout?scope=local", access_token=access_token)

    def user(self, access_token: str) -> dict[str, Any]:
        return self._request("GET", "/auth/v1/user", access_token=access_token)

    def table(self, access_token: str, table: str, *, query: str = "", method: str = "GET", payload: Any = None, prefer: str | None = None) -> Any:
        allowed = {"profiles", "fantasy_leagues", "fantasy_teams", "roster_slots", "roster_assignments", "team_preferences", "roster_change_log", "nfl_players", "sleeper_connections", "sleeper_sync_history", "sleeper_player_mappings"}
        if table not in allowed:
            raise ValueError("Unknown Command Center table")
        suffix = f"?{query}" if query else ""
        return self._request(method, f"/rest/v1/{table}{suffix}", access_token=access_token, json=payload, prefer=prefer)

    def rpc(self, access_token: str, function: str, payload: dict[str, Any]) -> Any:
        allowed = {"begin_sleeper_sync", "record_sleeper_sync_result", "resolve_sleeper_sync", "swap_roster_players"}
        if function not in allowed:
            raise ValueError("Unknown Command Center function")
        return self._request("POST", f"/rest/v1/rpc/{function}", access_token=access_token, json=payload)

