"""Read-only Sleeper roster discovery and deterministic player mapping."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import pandas as pd
import requests


class SleeperError(RuntimeError):
    """A user-safe Sleeper integration failure."""


@dataclass(frozen=True)
class SleeperLeague:
    league_id: str
    name: str
    season: int
    roster_positions: tuple[str, ...]
    scoring_settings: dict[str, Any]


class SleeperClient:
    """Small read-only client. It never accepts or sends Sleeper credentials."""

    base_url = "https://api.sleeper.app/v1"

    def __init__(self, timeout: tuple[float, float] = (3.05, 10), session: requests.Session | None = None) -> None:
        self.timeout = timeout
        self.http = session or requests.Session()

    def _get(self, path: str) -> Any:
        for attempt in range(3):
            try:
                response = self.http.get(f"{self.base_url}{path}", timeout=self.timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        retry_after = response.headers.get("Retry-After", "")
                        delay = min(float(retry_after), 2.0) if retry_after.replace(".", "", 1).isdigit() else 0.25 * (2**attempt)
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError):
                if attempt < 2:
                    time.sleep(0.25 * (2**attempt))
                    continue
        raise SleeperError("Sleeper is temporarily unavailable. Your saved team was not changed.") from None

    def user(self, username: str) -> dict[str, Any]:
        clean = username.strip()
        if not clean or len(clean) > 50:
            raise SleeperError("Enter a valid Sleeper username.")
        payload = self._get(f"/user/{clean}")
        if not payload or not payload.get("user_id"):
            raise SleeperError("No Sleeper account was found for that username.")
        return payload

    def leagues(self, user_id: str, season: int) -> list[SleeperLeague]:
        rows = self._get(f"/user/{user_id}/leagues/nfl/{int(season)}") or []
        return [SleeperLeague(str(row["league_id"]), str(row.get("name") or "Sleeper league"), int(row.get("season") or season), tuple(row.get("roster_positions") or ()), dict(row.get("scoring_settings") or {})) for row in rows]

    def league(self, league_id: str) -> SleeperLeague:
        row = self._get(f"/league/{league_id}") or {}
        if not row.get("league_id"):
            raise SleeperError("That Sleeper league is no longer available. Your saved team was not changed.")
        return SleeperLeague(str(row["league_id"]), str(row.get("name") or "Sleeper league"), int(row.get("season") or 0), tuple(row.get("roster_positions") or ()), dict(row.get("scoring_settings") or {}))

    def roster(self, league_id: str, user_id: str) -> dict[str, Any]:
        rows = self._get(f"/league/{league_id}/rosters") or []
        row = next((item for item in rows if str(item.get("owner_id")) == str(user_id)), None)
        if not row:
            raise SleeperError("That Sleeper league does not contain a roster owned by this account.")
        return row

    def players(self) -> dict[str, dict[str, Any]]:
        return self._get("/players/nfl") or {}


def roster_shape(positions: tuple[str, ...]) -> tuple[dict[str, int], list[str]]:
    """Translate Sleeper slots into the formats currently supported by SDL."""
    aliases = {"W/R/T": "FLEX", "WRRB_FLEX": "FLEX", "REC_FLEX": "FLEX", "SUPER_FLEX": "SUPERFLEX", "BN": "BENCH"}
    supported = {"QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "BENCH"}
    counts = {slot: 0 for slot in supported}
    ignored: list[str] = []
    for raw in positions:
        slot = aliases.get(str(raw).upper(), str(raw).upper())
        if slot in supported:
            counts[slot] += 1
        else:
            ignored.append(str(raw))
    return counts, ignored


def passing_td_points(scoring: dict[str, Any]) -> tuple[int, str | None]:
    value = float(scoring.get("pass_td", 4) or 4)
    if value in {4.0, 6.0}:
        return int(value), None
    return 4, f"Sleeper uses {value:g}-point passing TDs; SDL currently supports 4 or 6. This import defaults to 4 until you edit the league setting."


def map_players(roster_ids: list[str], sleeper_players: dict[str, dict[str, Any]], board: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Map via GSIS ID first, then an unambiguous name/position fallback."""
    board_rows = board.drop_duplicates("player_id").copy()
    by_id = {str(row.player_id): str(row.player_id) for row in board_rows.itertuples()}
    by_name: dict[tuple[str, str], list[str]] = {}
    for row in board_rows.itertuples():
        key = (str(row.player).strip().casefold(), str(row.position).upper())
        by_name.setdefault(key, []).append(str(row.player_id))
    mapped, unmatched = [], []
    for sleeper_id in roster_ids:
        source = sleeper_players.get(str(sleeper_id), {})
        gsis = str(source.get("gsis_id") or "")
        candidate = by_id.get(gsis)
        if not candidate:
            name = str(source.get("full_name") or "").strip().casefold()
            position = str(source.get("position") or "").upper()
            matches = by_name.get((name, position), [])
            candidate = matches[0] if len(matches) == 1 else None
        if candidate:
            mapped.append(candidate)
        else:
            unmatched.append(str(source.get("full_name") or sleeper_id))
    return mapped, unmatched


def map_player_records(roster_ids: list[str], sleeper_players: dict[str, dict[str, Any]], board: pd.DataFrame) -> list[dict[str, Any]]:
    """Return auditable external-to-SDL mappings without guessing ambiguous players."""
    board_rows = board.drop_duplicates("player_id").copy()
    by_id = {str(row.player_id): str(row.player_id) for row in board_rows.itertuples()}
    by_name: dict[tuple[str, str], list[str]] = {}
    for row in board_rows.itertuples():
        by_name.setdefault((str(row.player).strip().casefold(), str(row.position).upper()), []).append(str(row.player_id))
    records: list[dict[str, Any]] = []
    for sleeper_id in dict.fromkeys(str(value) for value in roster_ids if value):
        source = sleeper_players.get(sleeper_id, {})
        gsis = str(source.get("gsis_id") or "")
        mapped = by_id.get(gsis)
        method = "gsis_id" if mapped else None
        if not mapped:
            matches = by_name.get((str(source.get("full_name") or "").strip().casefold(), str(source.get("position") or "").upper()), [])
            if len(matches) == 1:
                mapped, method = matches[0], "unique_name_position"
        records.append(
            {
                "external_player_id": sleeper_id,
                "player_id": mapped,
                "name": str(source.get("full_name") or sleeper_id),
                "position": str(source.get("position") or ""),
                "team": str(source.get("team") or ""),
                "match_method": method,
                "matched": bool(mapped),
            }
        )
    return records
