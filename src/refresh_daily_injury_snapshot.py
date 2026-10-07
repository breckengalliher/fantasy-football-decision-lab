"""Publish the free daily injury/practice snapshot for the hosted app."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.data import build_start_sit_board, current_nfl_season, load_live_weekly_data
from dashboard.providers.injuries import load_daily_injury_context


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
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
