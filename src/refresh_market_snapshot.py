"""Refresh supplemental player-prop expectations without rebuilding projections."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.market_expectations import enrich_with_market
from dashboard.providers.sportsdataio import SportsDataIOClient
from src.refresh_weekly_snapshot import PROCESSED, api_key, atomic_parquet


MARKET_COLUMNS = [
    "market_receptions", "market_receiving_yards", "market_rushing_yards",
    "market_passing_yards", "market_passing_tds", "market_rushing_receiving_tds",
    "market_interceptions", "market_book_count", "market_updated_at",
    "market_implied_ppr", "market_available", "market_checked_at",
]


def target_interval(now: datetime) -> timedelta:
    """Use the fastest cadence during the primary NFL lineup windows."""
    central = now.astimezone(ZoneInfo("America/Chicago"))
    weekday = central.weekday()  # Monday=0
    if weekday in {6, 0} and 8 <= central.hour < 23:
        return timedelta(minutes=30)
    if weekday == 5:
        return timedelta(hours=1)
    if weekday in {3, 4}:
        return timedelta(hours=2)
    return timedelta(hours=6)


def refresh_due(last_refresh: str | None, now: datetime) -> bool:
    if not last_refresh:
        return True
    try:
        previous = datetime.fromisoformat(str(last_refresh).replace("Z", "+00:00"))
    except ValueError:
        return True
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc) - previous.astimezone(timezone.utc) >= target_interval(now)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ignore adaptive cadence for an admin refresh.")
    args = parser.parse_args()
    metadata_path = PROCESSED / "live_refresh_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    if not args.force and not refresh_due(metadata.get("market_refreshed_at"), now):
        print(json.dumps({"status": "skipped", "reason": "adaptive cadence", "next_interval_minutes": int(target_interval(now).total_seconds() / 60)}))
        return
    key = api_key()
    if not key:
        raise RuntimeError("SPORTSDATAIO_API_KEY is not configured.")
    season, week = int(metadata["season"]), int(metadata["next_week"])
    lines, status, refreshed_at = SportsDataIOClient(key).weekly_market_lines(season, week)
    if status.startswith("Temporarily unavailable"):
        metadata.update({"market_status": status, "market_last_attempted_at": refreshed_at})
        temporary = metadata_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        temporary.replace(metadata_path)
        print(json.dumps({"status": status, "preserved": True}))
        return
    for points in (4, 6):
        path = PROCESSED / f"live_start_sit_board_{points}pt_current.parquet"
        board = pd.read_parquet(path).drop(columns=MARKET_COLUMNS, errors="ignore")
        refreshed = enrich_with_market(board, lines, points)
        atomic_parquet(refreshed, path)
        if points == 4:
            atomic_parquet(refreshed, PROCESSED / "live_start_sit_board_current.parquet")
    metadata.update({
        "market_refreshed_at": refreshed_at,
        "market_status": status,
        "market_refresh_interval_minutes": int(target_interval(now).total_seconds() / 60),
    })
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temporary.replace(metadata_path)
    print(json.dumps({"status": status, "season": season, "week": week, "refreshed_at": refreshed_at}))


if __name__ == "__main__":
    main()
