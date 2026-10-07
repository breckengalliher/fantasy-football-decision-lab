"""Collect daily evidence for a full-week injury/practice coverage audit."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.data import build_start_sit_board, current_nfl_season, load_live_weekly_data
from dashboard.providers.sportsdataio import SportsDataIOClient
from src.refresh_weekly_snapshot import api_key


def coverage_observation(
    eligible: pd.DataFrame,
    injuries: pd.DataFrame,
    refreshed_at: str,
    observed_at: datetime | None = None,
) -> dict:
    """Summarize provider completeness without treating no injury record as healthy."""
    now = observed_at or datetime.now(timezone.utc)
    player_keys = set(zip(eligible["player_key"], eligible["team"]))
    records = injuries.copy()
    if records.empty:
        records = pd.DataFrame(columns=[
            "player_key", "team", "injury_status_live", "practice_status_live", "injury_updated_live"
        ])
    matched = records.apply(lambda row: (row["player_key"], row["team"]) in player_keys, axis=1)
    relevant = records.loc[matched].copy()
    duplicate_count = int(records.duplicated(["player_key", "team"], keep=False).sum())

    def complete(column: str) -> int:
        return int(relevant[column].notna().sum()) if column in relevant else 0

    return {
        "observed_at": now.isoformat(),
        "provider_refreshed_at": refreshed_at,
        "eligible_players": int(len(eligible)),
        "provider_injury_records": int(len(records)),
        "matched_relevant_records": int(len(relevant)),
        "unmatched_provider_records": int((~matched).sum()),
        "duplicate_player_team_records": duplicate_count,
        "status_complete_records": complete("injury_status_live"),
        "practice_complete_records": complete("practice_status_live"),
        "updated_timestamp_complete_records": complete("injury_updated_live"),
        "status_completeness": round(complete("injury_status_live") / len(relevant), 4) if len(relevant) else None,
        "practice_completeness": round(complete("practice_status_live") / len(relevant), 4) if len(relevant) else None,
        "timestamp_completeness": round(complete("injury_updated_live") / len(relevant), 4) if len(relevant) else None,
        "semantic_coverage_pass": bool(
            len(relevant)
            and complete("injury_status_live") == len(relevant)
            and complete("practice_status_live") == len(relevant)
            and duplicate_count == 0
        ),
        "status_values": sorted(relevant.get("injury_status_live", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()),
        "practice_values": sorted(relevant.get("practice_status_live", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()),
        "validation_note": "Provider placeholders such as Scrambled, Redacted, and Unavailable count as missing.",
    }


def main() -> None:
    season = current_nfl_season()
    weekly, schedules = load_live_weekly_data(season)
    board, next_week = build_start_sit_board(weekly, schedules, season)
    eligible = board.loc[board["is_roster_relevant"] & board["next_opponent"].notna(), ["player", "team"]].copy()
    eligible["player_key"] = eligible["player"].str.strip().str.casefold()

    key = api_key()
    if not key:
        raise RuntimeError("SPORTSDATAIO_API_KEY is not configured.")
    context = SportsDataIOClient(key).weekly_context(season, next_week)
    observation = coverage_observation(eligible, context.injuries, context.refreshed_at)

    path = ROOT / "reports" / f"injury-practice-coverage-{season}-week-{next_week}.json"
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
    else:
        report = {
            "season": season,
            "week": next_week,
            "purpose": "Full-week validation of live injury and practice coverage; missing injury records are never interpreted as healthy.",
            "observations": [],
        }
    report["observations"].append(observation)
    report["latest"] = observation
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(path)
    print(json.dumps(observation))


if __name__ == "__main__":
    main()
