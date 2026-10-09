"""Retrieve real context into a new disposable directory; never publish remotely."""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard.providers.injuries import load_daily_injury_context
from dashboard.providers.sportsdataio import SportsDataIOClient
from dashboard.football_integrity import reconcile_board_identities
from src.refresh_live_context import refresh_board
from src.refresh_weekly_snapshot import api_key
from src.publication import FILES, validate_snapshot


def main():
    started = datetime.now(timezone.utc)
    destination = ROOT / "reports/production-certification-20261009" / started.strftime("controlled-refresh-%H%M%S")
    destination.mkdir(exist_ok=False)
    source = ROOT / "data/processed"
    metadata = json.loads((source / "live_refresh_metadata.json").read_text())
    season, week = int(metadata["season"]), int(metadata["next_week"])
    provider = SportsDataIOClient(api_key()).weekly_context(season, week)
    injuries = load_daily_injury_context(season, week)
    if injuries.records.empty or not injuries.nflverse_status.startswith("Connected"):
        raise ValueError("Injury retrieval incomplete; controlled refresh rejected")
    evidence = {"started_at": started.isoformat(), "scope": "Disposable local data only; not remote publication or browser certification", "scoring": {}}
    columns = ["floor_ppr", "median_ppr", "ceiling_ppr", "projected_ppr"]
    for points in (4, 6):
        filename = f"live_start_sit_board_{points}pt_current.parquet"
        raw = pd.read_parquet(source / filename)
        before = reconcile_board_identities(raw)
        after = refresh_board(before, provider, injuries, passing_td_points=points)
        original = before.set_index("player_id")[columns].sort_index()
        updated = after.set_index("player_id").loc[original.index, columns].sort_index()
        pd.testing.assert_frame_equal(original, updated, check_dtype=False)
        after.to_parquet(destination / filename, index=False)
        evidence["scoring"][str(points)] = {"rows": len(after), "original_rows": len(before), "approved_exact_identity_repairs": int(raw.player_id.ne(before.player_id).sum()), "original_projections_exactly_preserved": True, "unique_columns": after.columns.is_unique}
    shutil.copy2(source / "live_weekly_current.parquet", destination / "live_weekly_current.parquet")
    metadata.update({"context_refreshed_at": datetime.now(timezone.utc).isoformat(),
        "injury_refreshed_at": injuries.checked_at, "injury_source_updated_at": injuries.provider_updated_at,
        "injury_official_report_at": injuries.official_report_at, "injury_freshness_verified": injuries.freshness_verified,
        "depth_source_updated_at": provider.depth_source_updated_at, "depth_freshness_verified": provider.depth_freshness_verified,
        "sportsdataio_refreshed_at": provider.refreshed_at})
    (destination / "live_refresh_metadata.json").write_text(json.dumps(metadata, indent=2))
    validated = validate_snapshot(destination)
    evidence.update({"validation": "passed", "counts": validated["record_counts"],
        "injury_freshness_verified": injuries.freshness_verified, "depth_freshness_verified": provider.depth_freshness_verified,
        "destination": str(destination), "completed_at": datetime.now(timezone.utc).isoformat()})
    (destination / "evidence.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
