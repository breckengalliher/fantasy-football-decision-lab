"""Current-roster player headshots resolved during the cloud refresh."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests


SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl?active=true"
SLEEPER_HEADSHOT_URL = "https://sleepercdn.com/content/nfl/players/{player_id}.jpg"
SUPPORTED_POSITIONS = {"QB", "RB", "WR", "TE"}
TEAM_ALIASES = {"LAR": "LA"}


@dataclass(frozen=True)
class HeadshotContext:
    records: pd.DataFrame
    checked_at: str
    status: str


def _key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def normalize_headshots(payload: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Create one unambiguous active-roster photo mapping per player/team."""
    rows = []
    for fallback_id, player in (payload or {}).items():
        player_id = str(player.get("player_id") or fallback_id or "").strip()
        name = player.get("full_name") or " ".join(
            str(value).strip() for value in (player.get("first_name"), player.get("last_name")) if value
        )
        team = str(player.get("team") or "").strip().upper()
        team = TEAM_ALIASES.get(team, team)
        position = str(player.get("position") or "").strip().upper()
        if not player_id or not name or not team or position not in SUPPORTED_POSITIONS or player.get("active") is False:
            continue
        rows.append({
            "player_key": _key(name),
            "team": team,
            "position": position,
            "headshot_url": SLEEPER_HEADSHOT_URL.format(player_id=player_id),
            "headshot_source": "Sleeper active NFL roster",
        })
    if not rows:
        return pd.DataFrame(columns=["player_key", "team", "position", "headshot_url", "headshot_source"])
    records = pd.DataFrame(rows)
    unique = ~records.duplicated(["player_key", "team", "position"], keep=False)
    return records.loc[unique].reset_index(drop=True)


def load_headshot_context(timeout: int = 30) -> HeadshotContext:
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        response = requests.get(SLEEPER_PLAYERS_URL, timeout=timeout)
        response.raise_for_status()
        records = normalize_headshots(response.json())
        return HeadshotContext(records, checked_at, f"Connected · {len(records)} active roster photos")
    except Exception as error:
        empty = normalize_headshots({})
        return HeadshotContext(empty, checked_at, f"Connection error · {type(error).__name__}")


def enrich_with_headshots(board: pd.DataFrame, context: HeadshotContext) -> pd.DataFrame:
    result = board.copy()
    result["player_key"] = result["player"].map(_key)
    if not context.records.empty:
        result = result.merge(context.records, on=["player_key", "team", "position"], how="left")
    else:
        result["headshot_url"] = pd.NA
        result["headshot_source"] = pd.NA
    return result.drop(columns="player_key")
