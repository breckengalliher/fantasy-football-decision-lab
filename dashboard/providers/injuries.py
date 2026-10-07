"""Free daily injury context from nflverse with a Sleeper status fallback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
import json

import pandas as pd
import requests

try:
    from dashboard.providers.sportsdataio import canonical_injury_status
except ModuleNotFoundError:
    from providers.sportsdataio import canonical_injury_status

NFLVERSE_INJURIES = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.parquet"
SLEEPER_PLAYERS = "https://api.sleeper.app/v1/players/nfl?active=true"
WEEKLY_STATUSES = {"Questionable", "Doubtful", "Out", "Inactive"}
RESERVE_STATUSES = {"IR", "PUP"}


@dataclass(frozen=True)
class InjuryContext:
    records: pd.DataFrame
    checked_at: str
    nflverse_status: str
    sleeper_status: str


def _key(value: Any) -> str:
    return str(value).strip().casefold()


def normalize_nflverse_injuries(frame: pd.DataFrame, week: int) -> pd.DataFrame:
    data = frame.copy()
    if "season_type" in data:
        data = data.loc[data["season_type"].eq("REG")]
    data = data.loc[data["week"].eq(week)].copy()
    if data.empty:
        return pd.DataFrame()
    data["player_key"] = data["full_name"].map(_key)
    data["injury_record_live"] = True
    data["injury_status_live"] = data["report_status"].map(canonical_injury_status)
    data["practice_status_live"] = data["practice_status"]
    data["injury_body_part_live"] = data["report_primary_injury"].fillna(data["practice_primary_injury"])
    data["injury_note_live"] = pd.NA
    data["injury_updated_live"] = pd.NA
    data["injury_source_live"] = "nflverse daily injury report"
    data["injury_conflict_live"] = False
    columns = ["player_key", "team", "injury_record_live", "injury_status_live", "practice_status_live", "injury_body_part_live", "injury_note_live", "injury_updated_live", "injury_source_live", "injury_conflict_live"]
    return data[columns].drop_duplicates(["player_key", "team"], keep="last")


def normalize_sleeper_players(payload: dict[str, dict[str, Any]], now_ms: int | None = None) -> pd.DataFrame:
    now_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    rows = []
    for player in (payload or {}).values():
        name = player.get("full_name") or " ".join(value for value in (player.get("first_name"), player.get("last_name")) if value)
        team = player.get("team")
        status = canonical_injury_status(player.get("injury_status"))
        updated = pd.to_numeric(player.get("news_updated"), errors="coerce")
        max_age_days = 7 if status in WEEKLY_STATUSES else 30 if status in RESERVE_STATUSES else 0
        fresh = pd.notna(updated) and updated >= now_ms - max_age_days * 86_400_000
        if not name or not team or pd.isna(status) or not fresh:
            continue
        rows.append({"player_key": _key(name), "team": str(team), "sleeper_injury_status": status, "sleeper_news_updated": int(updated)})
    return pd.DataFrame(rows).drop_duplicates(["player_key", "team"], keep="last") if rows else pd.DataFrame()


def combine_injury_sources(nflverse: pd.DataFrame, sleeper: pd.DataFrame) -> pd.DataFrame:
    if nflverse.empty and sleeper.empty:
        return pd.DataFrame()
    if nflverse.empty:
        result = sleeper.copy()
        result["injury_record_live"] = True
        result["injury_status_live"] = result["sleeper_injury_status"]
        result["practice_status_live"] = pd.NA
        result["injury_body_part_live"] = pd.NA
        result["injury_note_live"] = pd.NA
        result["injury_updated_live"] = result["sleeper_news_updated"]
        result["injury_source_live"] = "Sleeper daily fallback"
        result["injury_conflict_live"] = False
    elif sleeper.empty:
        result = nflverse.copy()
    else:
        result = nflverse.merge(sleeper, on=["player_key", "team"], how="outer")
        nflverse_record = result["injury_record_live"].fillna(False).astype(bool)
        nflverse_status = result["injury_status_live"]
        sleeper_status = result["sleeper_injury_status"]
        fallback = nflverse_status.isna() & sleeper_status.notna()
        result.loc[fallback, "injury_status_live"] = result.loc[fallback, "sleeper_injury_status"]
        result.loc[~nflverse_record & fallback, "injury_record_live"] = True
        result.loc[~nflverse_record & fallback, "injury_source_live"] = "Sleeper daily fallback"
        result.loc[nflverse_record & fallback, "injury_source_live"] = "nflverse + Sleeper fallback"
        result["injury_conflict_live"] = nflverse_status.notna() & sleeper_status.notna() & nflverse_status.astype(str).ne(sleeper_status.astype(str))
        result.loc[result["injury_conflict_live"], "injury_source_live"] = "nflverse · Sleeper disagreement"
        result["injury_updated_live"] = result["injury_updated_live"].fillna(result["sleeper_news_updated"])
    keep = ["player_key", "team", "injury_record_live", "injury_status_live", "practice_status_live", "injury_body_part_live", "injury_note_live", "injury_updated_live", "injury_source_live", "injury_conflict_live"]
    return result[keep].drop_duplicates(["player_key", "team"], keep="last")


def load_daily_injury_context(season: int, week: int, timeout: int = 25) -> InjuryContext:
    nflverse = pd.DataFrame()
    sleeper = pd.DataFrame()
    nflverse_status = "Unavailable"
    sleeper_status = "Unavailable"
    try:
        raw = pd.read_parquet(NFLVERSE_INJURIES.format(season=season))
        nflverse = normalize_nflverse_injuries(raw, week)
        nflverse_status = f"Connected · {len(nflverse)} Week {week} records"
    except Exception as error:
        nflverse_status = f"Connection error · {type(error).__name__}"
    try:
        response = requests.get(SLEEPER_PLAYERS, timeout=timeout)
        response.raise_for_status()
        sleeper = normalize_sleeper_players(response.json())
        sleeper_status = f"Connected · {len(sleeper)} designated players"
    except Exception as error:
        sleeper_status = f"Connection error · {type(error).__name__}"
    return InjuryContext(combine_injury_sources(nflverse, sleeper), datetime.now(timezone.utc).isoformat(), nflverse_status, sleeper_status)


def enrich_injuries(board: pd.DataFrame, context: InjuryContext) -> pd.DataFrame:
    result = board.copy()
    result["player_key"] = result["player"].map(_key)
    if not context.records.empty:
        result = result.merge(context.records, on=["player_key", "team"], how="left")
    result["injury_checked_at"] = context.checked_at
    return result.drop(columns="player_key")


def load_persisted_injury_context(root: Path, season: int, week: int, max_age_hours: int = 36) -> InjuryContext | None:
    """Load the cloud-published snapshot only when it matches and is fresh."""
    parquet = root / "data" / "processed" / "daily_injury_context_current.parquet"
    metadata_path = root / "data" / "processed" / "daily_injury_context_metadata.json"
    if not parquet.exists() or not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        checked = datetime.fromisoformat(str(metadata["checked_at"]).replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds() / 3600
        if metadata.get("season") != season or metadata.get("week") != week or age_hours > max_age_hours:
            return None
        return InjuryContext(
            pd.read_parquet(parquet),
            metadata["checked_at"],
            metadata["nflverse_status"],
            metadata["sleeper_status"],
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None
