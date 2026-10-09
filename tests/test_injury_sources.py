import json
from datetime import datetime, timezone

import pandas as pd

from dashboard.providers.injuries import InjuryContext, combine_injury_sources, load_persisted_injury_context, normalize_nflverse_injuries, normalize_sleeper_players


def test_nflverse_normalization_keeps_report_and_practice_fields():
    raw = pd.DataFrame([{
        "season_type": "REG", "week": 5, "full_name": "Example Receiver", "team": "SEA",
        "report_status": "Questionable", "practice_status": "Limited Participation in Practice",
        "report_primary_injury": "Hamstring", "practice_primary_injury": "Hamstring",
    }])
    result = normalize_nflverse_injuries(raw, 5)
    assert result.loc[0, "injury_status_live"] == "Questionable"
    assert result.loc[0, "practice_status_live"] == "Limited Participation in Practice"
    assert result.loc[0, "injury_source_live"] == "nflverse daily injury report"


def test_sleeper_only_fills_missing_nflverse_designation():
    nflverse = pd.DataFrame([{
        "player_key": "example receiver", "team": "SEA", "injury_record_live": True,
        "injury_status_live": pd.NA, "practice_status_live": "Limited", "injury_body_part_live": "Hamstring",
        "injury_note_live": pd.NA, "injury_updated_live": pd.NA,
        "injury_source_live": "nflverse daily injury report", "injury_conflict_live": False,
    }])
    sleeper = normalize_sleeper_players({"1": {"full_name": "Example Receiver", "team": "SEA", "injury_status": "Questionable", "news_updated": 1}}, now_ms=1)
    result = combine_injury_sources(nflverse, sleeper)
    assert result.loc[0, "injury_status_live"] == "Questionable"
    assert result.loc[0, "injury_source_live"] == "nflverse + Sleeper fallback"


def test_nflverse_wins_and_disagreement_is_visible():
    nflverse = pd.DataFrame([{
        "player_key": "example receiver", "team": "SEA", "injury_record_live": True,
        "injury_status_live": "Doubtful", "practice_status_live": "DNP", "injury_body_part_live": "Knee",
        "injury_note_live": pd.NA, "injury_updated_live": pd.NA,
        "injury_source_live": "nflverse daily injury report", "injury_conflict_live": False,
    }])
    sleeper = normalize_sleeper_players({"1": {"full_name": "Example Receiver", "team": "SEA", "injury_status": "Questionable", "news_updated": 1}}, now_ms=1)
    result = combine_injury_sources(nflverse, sleeper)
    assert result.loc[0, "injury_status_live"] == "Doubtful"
    assert bool(result.loc[0, "injury_conflict_live"])
    assert "disagreement" in result.loc[0, "injury_source_live"]


def test_stale_or_unsupported_sleeper_labels_are_rejected():
    payload = {
        "1": {"full_name": "Stale Player", "team": "SEA", "injury_status": "Questionable", "news_updated": 1},
        "2": {"full_name": "Unsupported Player", "team": "SEA", "injury_status": "NA", "news_updated": 1000},
    }
    assert normalize_sleeper_players(payload, now_ms=10 * 86_400_000).empty


def test_cloud_published_snapshot_must_match_season_and_week(tmp_path):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    pd.DataFrame([{"player_key": "alpha", "team": "SEA"}]).to_parquet(processed / "daily_injury_context_current.parquet")
    metadata = {
        "season": 2026, "week": 5, "checked_at": datetime.now(timezone.utc).isoformat(),
        "nflverse_status": "Connected", "sleeper_status": "Connected",
    }
    (processed / "daily_injury_context_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    assert isinstance(load_persisted_injury_context(tmp_path, 2026, 5), InjuryContext)
    assert load_persisted_injury_context(tmp_path, 2026, 6) is None
