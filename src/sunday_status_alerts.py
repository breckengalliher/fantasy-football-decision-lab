"""Detect meaningful injury/practice transitions for Sunday alerts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

INJURY_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.parquet"
REPORT_ALERTS = {"Questionable", "Doubtful", "Out", "IR", "PUP"}
PRACTICE_SEVERITY = {
    "Full Participation in Practice": 0,
    "Limited Participation in Practice": 1,
    "Did Not Participate In Practice": 2,
}
ROOT = Path(__file__).resolve().parents[1]


def meaningful_status_changes(previous: pd.DataFrame, current: pd.DataFrame) -> list[dict]:
    """Return only report-status transitions and practice downgrades."""
    keys = ["gsis_id", "team"]
    old = previous[keys + ["full_name", "report_status", "practice_status"]].drop_duplicates(keys)
    new = current[keys + ["full_name", "report_status", "practice_status"]].drop_duplicates(keys)
    joined = old.merge(new, on=keys, suffixes=("_old", "_new"))
    alerts = []
    for row in joined.itertuples(index=False):
        old_report = row.report_status_old if pd.notna(row.report_status_old) else None
        new_report = row.report_status_new if pd.notna(row.report_status_new) else None
        old_practice = row.practice_status_old if pd.notna(row.practice_status_old) else None
        new_practice = row.practice_status_new if pd.notna(row.practice_status_new) else None
        report_changed = old_report != new_report and new_report in REPORT_ALERTS
        practice_downgrade = (
            old_practice in PRACTICE_SEVERITY
            and new_practice in PRACTICE_SEVERITY
            and PRACTICE_SEVERITY[new_practice] > PRACTICE_SEVERITY[old_practice]
        )
        if report_changed or practice_downgrade:
            alerts.append({
                "player": row.full_name_new,
                "team": row.team,
                "old_report_status": old_report,
                "new_report_status": new_report,
                "old_practice_status": old_practice,
                "new_practice_status": new_practice,
                "reason": "report status change" if report_changed else "practice downgrade",
            })
    return alerts


def main() -> None:
    season = 2026
    data = pd.read_parquet(INJURY_URL.format(season=season))
    if len(sys.argv) == 4 and sys.argv[1] == "--replay-weeks":
        old_week, new_week = map(int, sys.argv[2:])
        alerts = meaningful_status_changes(data.loc[data["week"].eq(old_week)], data.loc[data["week"].eq(new_week)])
        result = {"season": season, "old_week": old_week, "new_week": new_week, "alerts": alerts}
    elif len(sys.argv) == 2 and sys.argv[1] == "--monitor-current":
        current_week = int(data["week"].max())
        current = data.loc[data["week"].eq(current_week)].copy()
        snapshot = ROOT / "data" / "processed" / "sunday_injuries_current.parquet"
        previous = pd.read_parquet(snapshot) if snapshot.exists() else current.iloc[0:0].copy()
        alerts = meaningful_status_changes(previous, current) if not previous.empty else []
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = snapshot.with_suffix(".parquet.tmp")
        current.to_parquet(temporary, index=False)
        temporary.replace(snapshot)
        result = {"season": season, "week": current_week, "records": len(current), "baseline_created": previous.empty, "alerts": alerts}
    else:
        raise SystemExit("usage: sunday_status_alerts.py --replay-weeks OLD_WEEK NEW_WEEK | --monitor-current")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
