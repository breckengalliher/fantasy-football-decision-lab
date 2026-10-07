"""SportsDataIO adapter for supplementary, non-model decision context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd
import requests


BASE_URL = "https://api.sportsdata.io/v3/nfl"
CONTEXT_STALE_AFTER_MINUTES = 90


@dataclass(frozen=True)
class SportsDataIOContext:
    injuries: pd.DataFrame
    games: pd.DataFrame
    depth_charts: pd.DataFrame
    refreshed_at: str


def context_freshness(
    refreshed_at: str | None,
    now: datetime | None = None,
    stale_after_minutes: int = CONTEXT_STALE_AFTER_MINUTES,
) -> tuple[int | None, bool]:
    """Return whole-minute age and whether live decision context is stale."""
    if not refreshed_at:
        return None, True
    try:
        checked = datetime.fromisoformat(str(refreshed_at).replace("Z", "+00:00"))
    except ValueError:
        return None, True
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    age_minutes = max(0, int((current - checked.astimezone(timezone.utc)).total_seconds() // 60))
    return age_minutes, age_minutes > stale_after_minutes


def _first(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return pd.NA


def _key(value: Any) -> str:
    return str(value).strip().casefold()


def _usable(value: Any) -> Any:
    """Reject provider placeholders that look populated but contain no information."""
    if pd.isna(value) or str(value).strip().casefold() in {"scrambled", "redacted", "unavailable"}:
        return pd.NA
    return value


class SportsDataIOClient:
    def __init__(self, api_key: str, timeout: int = 20) -> None:
        if not api_key.strip():
            raise ValueError("SportsDataIO API key is empty.")
        self.api_key = api_key.strip()
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        response = requests.get(
            f"{BASE_URL}/{path.lstrip('/')}",
            params={"key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def weekly_context(self, season: int, week: int) -> SportsDataIOContext:
        season_code = f"{season}REG"
        injuries = self._get(f"stats/json/Injuries/{season_code}/{week}")
        games = self._get(f"scores/json/ScoresByWeek/{season_code}/{week}")
        depth = self._get("scores/json/DepthChartsAll")
        teams = self._get("scores/json/Teams")
        team_map = {
            item.get("TeamID"): item.get("Key")
            for item in teams or []
            if item.get("TeamID") is not None and item.get("Key")
        }
        return SportsDataIOContext(
            injuries=normalize_injuries(injuries),
            games=normalize_games(games),
            depth_charts=normalize_depth_charts(depth, team_map),
            refreshed_at=datetime.now(timezone.utc).isoformat(),
        )


def normalize_injuries(payload: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in payload or []:
        name = _first(item, "Name", "PlayerName", "Player")
        team = _first(item, "Team", "TeamKey")
        if pd.isna(name) or pd.isna(team):
            continue
        rows.append(
            {
                "player_key": _key(name),
                "team": str(team),
                "injury_status_live": _usable(_first(item, "Status", "InjuryStatus")),
                "practice_status_live": _usable(_first(item, "Practice", "PracticeStatus")),
                "injury_body_part_live": _usable(_first(item, "BodyPart", "InjuredBodyPart")),
                "injury_note_live": _usable(_first(item, "Notes", "Note")),
                "injury_position": _first(item, "Position"),
                "injury_updated_live": _usable(_first(item, "Updated", "LastUpdated", "UpdatedDate")),
            }
        )
    return pd.DataFrame(rows)


def normalize_games(payload: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in payload or []:
        home = _first(item, "HomeTeam")
        away = _first(item, "AwayTeam")
        if pd.isna(home) or pd.isna(away):
            continue
        weather = _first(item, "ForecastDescription", "WeatherDescription")
        temperature = _first(item, "ForecastTempLow", "Temperature")
        wind = _first(item, "ForecastWindSpeed", "WindSpeed")
        total = _first(item, "OverUnder", "OverUnderDisplay")
        for team, opponent in [(home, away), (away, home)]:
            rows.append(
                {
                    "team": str(team),
                    "provider_opponent": str(opponent),
                    "weather_summary_live": weather,
                    "temperature_live": temperature,
                    "wind_live": wind,
                    "betting_total_live": total,
                    "game_status_live": _first(item, "Status"),
                    "game_updated_live": _first(item, "Updated", "DateTimeUTC", "DateTime"),
                }
            )
    return pd.DataFrame(rows)


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def normalize_depth_charts(
    payload: Any, team_map: dict[Any, str] | None = None
) -> pd.DataFrame:
    rows = []
    seen: set[tuple[str, str]] = set()
    for item in _walk(payload or []):
        name = _first(item, "Name", "PlayerName")
        team = _first(item, "Team", "TeamKey")
        if pd.isna(team) and team_map:
            team = team_map.get(item.get("TeamID"), pd.NA)
        if pd.isna(name) or pd.isna(team):
            continue
        pair = (_key(name), str(team))
        if pair in seen:
            continue
        seen.add(pair)
        rows.append(
            {
                "player_key": pair[0],
                "team": pair[1],
                "depth_position_live": _first(item, "Position", "DepthChartPosition"),
                "depth_order_live": _first(item, "DepthOrder", "DepthChartOrder"),
            }
        )
    return pd.DataFrame(rows)


def enrich_board(board: pd.DataFrame, context: SportsDataIOContext) -> pd.DataFrame:
    """Join provider context without modifying any projection columns."""
    result = board.copy()
    result["player_key"] = result["player"].map(_key)
    if not context.injuries.empty:
        result = result.merge(context.injuries, on=["player_key", "team"], how="left")
    if not context.depth_charts.empty:
        result = result.merge(context.depth_charts, on=["player_key", "team"], how="left")
    if not context.games.empty:
        result = result.merge(context.games, on="team", how="left")
    result["sportsdataio_refreshed_at"] = context.refreshed_at
    return result.drop(columns="player_key")
