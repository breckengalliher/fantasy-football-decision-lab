"""Refresh volatile decision context without recalculating projections."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.headshots import enrich_with_headshots, load_headshot_context
from dashboard.market_expectations import enrich_with_market
from dashboard.providers.injuries import enrich_injuries, load_daily_injury_context
from dashboard.providers.sportsdataio import SportsDataIOClient, add_depth_chart_promotions, enrich_board
from dashboard.football_integrity import reconcile_board_identities, guard_forecasts
from dashboard.reporting import enrich_with_reporting, load_reporting_context
from dashboard.snapshots import build_personnel_context
from src.refresh_weekly_snapshot import PROCESSED, api_key, atomic_parquet
from src.context_ledger import append_context_snapshot, build_context_snapshot


INJURY_COLUMNS = [
    "injury_record_live", "injury_status_live", "practice_status_live",
    "injury_body_part_live", "injury_note_live", "injury_updated_live",
    "injury_source_live", "injury_conflict_live", "injury_checked_at",
]
PROVIDER_COLUMNS = [
    "depth_position_live", "depth_order_live", "provider_opponent",
    "weather_summary_live", "temperature_live", "wind_live",
    "betting_total_live", "game_status_live", "game_updated_live",
    "provider_game_id", "sportsdataio_refreshed_at",
]
MARKET_COLUMNS = [
    "market_receptions", "market_receiving_yards", "market_rushing_yards",
    "market_passing_yards", "market_passing_tds", "market_rushing_receiving_tds",
    "market_interceptions", "market_book_count", "market_updated_at",
    "market_implied_ppr", "market_available", "market_checked_at",
]
REPORTING_COLUMNS = ["reporting_summary", "reporting_sources_json", "reporting_checked_at"]
HEADSHOT_COLUMNS = ["headshot_url", "headshot_source"]
CONTEXT_LEDGER = ROOT / "data" / "context_ledger"


def refresh_board(
    board: pd.DataFrame,
    provider_context,
    injury_context,
    reporting_context=None,
    headshot_context=None,
    passing_td_points: int = 4,
) -> pd.DataFrame:
    """Replace only informational fields, preserving existing model outputs."""
    board = reconcile_board_identities(board)
    projection_columns = [
        column for column in ("floor_ppr", "median_ppr", "ceiling_ppr", "projected_ppr")
        if column in board.columns
    ]
    frozen = board.set_index("player_id")[projection_columns].copy()
    result = board.drop(columns=INJURY_COLUMNS + PROVIDER_COLUMNS + MARKET_COLUMNS, errors="ignore")
    if reporting_context is not None:
        result = result.drop(columns=REPORTING_COLUMNS, errors="ignore")
    if headshot_context is not None:
        result = result.drop(columns=HEADSHOT_COLUMNS, errors="ignore")
    result = add_depth_chart_promotions(result, provider_context)
    result = enrich_injuries(result, injury_context)
    result = enrich_board(result, provider_context)
    result = enrich_with_market(result, provider_context.market_lines, passing_td_points)
    if reporting_context is not None:
        result = enrich_with_reporting(result, reporting_context)
    if headshot_context is not None:
        result = enrich_with_headshots(result, headshot_context)
    existing = result["player_id"].isin(frozen.index)
    for column in projection_columns:
        result.loc[existing, column] = result.loc[existing, "player_id"].map(frozen[column])
    return guard_forecasts(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-reporting", action="store_true")
    parser.add_argument("--include-headshots", action="store_true")
    args = parser.parse_args()
    metadata_path = PROCESSED / "live_refresh_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    season, week = int(metadata["season"]), int(metadata["next_week"])
    key = api_key()
    if not key:
        raise RuntimeError("SPORTSDATAIO_API_KEY is not configured.")
    provider_context = SportsDataIOClient(key).weekly_context(season, week)
    injury_context = load_daily_injury_context(season, week)
    if injury_context.records.empty or not injury_context.nflverse_status.startswith("Connected"):
        raise RuntimeError(f"Authoritative injury source unavailable: {injury_context.nflverse_status}")

    seed = pd.read_parquet(PROCESSED / "live_start_sit_board_4pt_current.parquet")
    reporting_context = load_reporting_context(seed) if args.include_reporting else None
    headshot_context = load_headshot_context() if args.include_headshots else None
    archived_board = None
    for points in (4, 6):
        path = PROCESSED / f"live_start_sit_board_{points}pt_current.parquet"
        refreshed = refresh_board(
            pd.read_parquet(path), provider_context, injury_context,
            reporting_context, headshot_context,
            passing_td_points=points,
        )
        atomic_parquet(refreshed, path)
        if points == 4:
            atomic_parquet(refreshed, PROCESSED / "live_start_sit_board_current.parquet")
            archived_board = refreshed

    previous_path = PROCESSED / "sportsdataio_depth_current.parquet"
    previous = pd.read_parquet(previous_path) if previous_path.exists() else pd.DataFrame()
    players, teams = build_personnel_context(provider_context.depth_charts, previous)
    atomic_parquet(provider_context.depth_charts, previous_path)
    atomic_parquet(players, PROCESSED / "personnel_players_current.parquet")
    atomic_parquet(teams, PROCESSED / "personnel_teams_current.parquet")
    if reporting_context is not None:
        atomic_parquet(reporting_context.records, PROCESSED / "reporting_context_current.parquet")
        metadata.update({
            "reporting_refreshed_at": reporting_context.checked_at,
            "journalism_status": reporting_context.journalism_status,
            "reporter_social_status": reporting_context.social_status,
        })
    if headshot_context is not None:
        atomic_parquet(headshot_context.records, PROCESSED / "headshot_context_current.parquet")
        metadata.update({
            "headshot_refreshed_at": headshot_context.checked_at,
            "headshot_status": headshot_context.status,
        })
    metadata.update({
        "context_refreshed_at": datetime.now(timezone.utc).isoformat(),
        "injury_refreshed_at": injury_context.checked_at,
        "injury_source_updated_at": injury_context.provider_updated_at,
        "injury_official_report_at": injury_context.official_report_at,
        "injury_freshness_verified": injury_context.freshness_verified,
        "depth_source_updated_at": provider_context.depth_source_updated_at,
        "depth_source_version": provider_context.depth_source_version,
        "depth_source_version_kind": "sha256-provider-payload",
        "depth_oldest_source_updated_at": provider_context.depth_oldest_source_updated_at,
        "depth_timestamp_records": provider_context.depth_timestamp_records,
        "depth_records": int(len(provider_context.depth_charts)),
        "depth_freshness_verified": provider_context.depth_freshness_verified,
        "injury_records": int(len(injury_context.records)),
        "injury_source_status": {
            "nflverse": injury_context.nflverse_status,
            "sleeper": injury_context.sleeper_status,
        },
        "sportsdataio_refreshed_at": provider_context.refreshed_at,
        "sportsdataio_status": f"Connected · {provider_context.refreshed_at[:16].replace('T', ' ')} UTC",
        "market_status": provider_context.market_status,
        "market_refreshed_at": provider_context.refreshed_at,
        "refresh_scope": "Live context only; projections preserved",
    })
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temporary.replace(metadata_path)
    captured_at = metadata["context_refreshed_at"]
    context_snapshot = build_context_snapshot(
        archived_board, season=season, week=week, captured_at=captured_at
    )
    append_context_snapshot(context_snapshot, CONTEXT_LEDGER)
    print(json.dumps({"season": season, "week": week, "scope": metadata["refresh_scope"]}))


if __name__ == "__main__":
    main()
