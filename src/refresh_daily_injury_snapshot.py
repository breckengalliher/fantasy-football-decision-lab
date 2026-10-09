"""Publish the free daily injury/practice snapshot for the hosted app."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.data import build_start_sit_board, current_nfl_season, load_live_weekly_data
from dashboard.providers.injuries import enrich_injuries, load_daily_injury_context
from src.refresh_weekly_snapshot import atomic_parquet
from src.football_qa import require_no_hard_errors, validate_board


def main() -> None:
    season = current_nfl_season()
    weekly, schedules = load_live_weekly_data(season)
    _, week = build_start_sit_board(weekly, schedules, season)
    context = load_daily_injury_context(season, week)
    if context.records.empty or not context.nflverse_status.startswith("Connected"):
        raise RuntimeError(f"Authoritative injury source unavailable: {context.nflverse_status}")
    processed = ROOT / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    parquet = processed / "daily_injury_context_current.parquet"
    temporary_parquet = parquet.with_suffix(".parquet.tmp")
    context.records.to_parquet(temporary_parquet, index=False)
    temporary_parquet.replace(parquet)
    metadata = {
        "season": season,
        "week": week,
        "checked_at": context.checked_at,
        "records": int(len(context.records)),
        "nflverse_status": context.nflverse_status,
        "sleeper_status": context.sleeper_status,
    }
    metadata_path = processed / "daily_injury_context_metadata.json"
    temporary_metadata = metadata_path.with_suffix(".json.tmp")
    temporary_metadata.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temporary_metadata.replace(metadata_path)
    injury_columns = [
        "injury_record_live", "injury_status_live", "practice_status_live",
        "injury_body_part_live", "injury_note_live", "injury_updated_live",
        "injury_source_live", "injury_conflict_live", "injury_checked_at",
    ]
    refreshed_boards = {}
    for filename in (
        "live_start_sit_board_current.parquet",
        "live_start_sit_board_4pt_current.parquet",
        "live_start_sit_board_6pt_current.parquet",
    ):
        path = processed / filename
        if not path.exists():
            raise FileNotFoundError(f"Published weekly snapshot is missing: {filename}")
        board = pd.read_parquet(path).drop(columns=injury_columns, errors="ignore")
        refreshed_board = enrich_injuries(board, context)
        require_no_hard_errors(validate_board(refreshed_board))
        refreshed_boards[path] = refreshed_board
    for path, refreshed_board in refreshed_boards.items():
        atomic_parquet(refreshed_board, path)
    weekly_metadata_path = processed / "live_refresh_metadata.json"
    if not weekly_metadata_path.exists():
        raise FileNotFoundError("Published weekly refresh metadata is missing.")
    weekly_metadata = json.loads(weekly_metadata_path.read_text(encoding="utf-8"))
    weekly_metadata["injury_records"] = int(len(context.records))
    weekly_metadata["injury_source_status"] = {
        "nflverse": context.nflverse_status,
        "sleeper": context.sleeper_status,
    }
    weekly_metadata["injury_refreshed_at"] = context.checked_at
    temporary_weekly_metadata = weekly_metadata_path.with_suffix(".json.tmp")
    temporary_weekly_metadata.write_text(json.dumps(weekly_metadata, indent=2), encoding="utf-8")
    temporary_weekly_metadata.replace(weekly_metadata_path)
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
