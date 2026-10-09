"""Read-only provider verification: never writes published app snapshots."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter
import json
import sys
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard.providers.injuries import NFLVERSE_INJURIES, SLEEPER_PLAYERS, normalize_sleeper_players
from dashboard.providers.sportsdataio import SportsDataIOClient, normalize_depth_charts, normalize_games
from src.refresh_weekly_snapshot import api_key


def main():
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "season": 2026,
              "week": 5, "scope": "Read-only retrieval; retrieval time is NOT an official report timestamp.", "sources": {}}
    def check(name, operation):
        start = perf_counter()
        try:
            result["sources"][name] = {"status": "retrieved", **operation()}
        except Exception as exc:
            # Provider exception strings can include credential-bearing URLs.
            result["sources"][name] = {"status": "unverified", "error_type": type(exc).__name__}
        result["sources"][name]["seconds"] = round(perf_counter() - start, 3)

    def injuries():
        response = requests.get(NFLVERSE_INJURIES.format(season=2026), timeout=(5, 25))
        response.raise_for_status()
        frame = pd.read_parquet(BytesIO(response.content))
        current = frame.loc[frame.week.eq(5)]
        dates = {c: sorted(current[c].dropna().astype(str).unique().tolist())[-10:]
                 for c in current if any(term in c.lower() for term in ("date", "time", "day"))}
        return {"rows": len(frame), "current_week_rows": len(current), "source_date_fields": dates,
                "columns": frame.columns.tolist()}
    check("nflverse_injuries", injuries)

    def sleeper():
        response = requests.get(SLEEPER_PLAYERS, timeout=(5, 25))
        response.raise_for_status()
        normalized = normalize_sleeper_players(response.json())
        return {"recent_status_records": len(normalized), "source": "Third-party status, not official inactive confirmation"}
    check("sleeper_status", sleeper)

    def depth_schedule():
        client = SportsDataIOClient(api_key(), timeout=20)
        games = normalize_games(client._get("scores/json/ScoresByWeek/2026REG/5"))
        teams = client._get("scores/json/Teams")
        depth = normalize_depth_charts(client._get("scores/json/DepthChartsAll"),
                 {t["TeamID"]: t["Key"] for t in teams if t.get("TeamID") is not None and t.get("Key")})
        return {"games": len(games), "depth_records": len(depth),
                "depth_columns": depth.columns.tolist(), "game_columns": games.columns.tolist(),
                "official_freshness_confirmed": False,
                "caveat": "Current endpoint retrieval alone does not establish timestamped official depth/inactive freshness."}
    check("sportsdataio_depth_schedule", depth_schedule)
    destination = ROOT / "reports/release-certification-20261009"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "fresh-sources.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
