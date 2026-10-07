"""Refresh and atomically save the validated weekly Start/Sit snapshot."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import tomllib

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.data import (
    add_live_supplementary_context,
    apply_approved_projection_model,
    apply_verified_starter_gate,
    build_start_sit_board,
    current_nfl_season,
    load_live_context_data,
    load_live_weekly_data,
    load_prior_weekly_data,
)
from dashboard.providers.sportsdataio import SportsDataIOClient, enrich_board
from dashboard.snapshots import build_personnel_context


PROCESSED = ROOT / "data" / "processed"


def api_key() -> str:
    value = os.getenv("SPORTSDATAIO_API_KEY", "").strip()
    if value:
        return value
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        return str(tomllib.loads(path.read_text())["SPORTSDATAIO_API_KEY"]).strip()
    return ""


def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def main() -> None:
    season = current_nfl_season()
    weekly, schedules = load_live_weekly_data(season)
    board, next_week = build_start_sit_board(weekly, schedules, season)
    snaps, teams = load_live_context_data(season)
    board = add_live_supplementary_context(board, snaps, teams)

    key = api_key()
    if not key:
        raise RuntimeError("SPORTSDATAIO_API_KEY is not configured.")
    context = SportsDataIOClient(key).weekly_context(season, next_week)
    board = enrich_board(board, context)
    prior_weekly = load_prior_weekly_data(season)
    board = apply_approved_projection_model(board, weekly, prior_weekly, next_week, passing_td_points=4)
    board = apply_verified_starter_gate(board)

    previous_path = PROCESSED / "sportsdataio_depth_current.parquet"
    previous = pd.read_parquet(previous_path) if previous_path.exists() else pd.DataFrame()
    player_context, team_context = build_personnel_context(context.depth_charts, previous)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    atomic_parquet(board, PROCESSED / "live_start_sit_board_current.parquet")
    atomic_parquet(context.depth_charts, previous_path)
    atomic_parquet(player_context, PROCESSED / "personnel_players_current.parquet")
    atomic_parquet(team_context, PROCESSED / "personnel_teams_current.parquet")

    eligible = board.loc[board["is_roster_relevant"] & board["next_opponent"].notna()]
    metadata = {
        "season": season,
        "completed_week": int(weekly["week"].max()),
        "next_week": next_week,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "eligible_players": int(len(eligible)),
        "injury_records": int(len(context.injuries)),
        "depth_chart_players": int(len(context.depth_charts)),
        "snap_coverage": float(eligible["latest_snap_pct"].notna().mean()),
        "weather_coverage": float(eligible["weather_summary_live"].notna().mean()),
        "betting_total_coverage": float(eligible["betting_total_live"].notna().mean()),
        "depth_chart_coverage": float(eligible["depth_order_live"].notna().mean()),
        "verified_qb_starters": int(board.loc[board["position"].eq("QB") & board["verified_qb_starter"]].shape[0]),
        "unverified_relevant_qbs": int(board.loc[board["position"].eq("QB") & board["is_roster_relevant"] & ~board["verified_qb_starter"]].shape[0]),
        "projection_model": "Approved round-three live model",
        "default_qb_passing_td_points": 4,
    }
    metadata_path = PROCESSED / "live_refresh_metadata.json"
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, indent=2))
    temporary.replace(metadata_path)
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
