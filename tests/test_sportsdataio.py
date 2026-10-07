from datetime import datetime, timezone

from dashboard.providers.sportsdataio import context_freshness, normalize_depth_charts, normalize_games, normalize_injuries


def test_context_freshness_flags_old_or_missing_data():
    now = datetime(2026, 10, 11, 17, 0, tzinfo=timezone.utc)
    assert context_freshness("2026-10-11T16:00:00+00:00", now) == (60, False)
    assert context_freshness("2026-10-11T15:29:00+00:00", now) == (91, True)
    assert context_freshness(None, now) == (None, True)


def test_injury_payload_is_normalized_without_guessing_missing_fields():
    result = normalize_injuries([
        {"Name": "Example Receiver", "Team": "ABC", "Status": "Questionable", "BodyPart": "Hamstring", "PracticeStatus": "Limited"}
    ])
    assert result.loc[0, "player_key"] == "example receiver"
    assert result.loc[0, "injury_status_live"] == "Questionable"
    assert result.loc[0, "practice_status_live"] == "Limited"


def test_game_context_is_available_to_both_teams():
    result = normalize_games([
        {"HomeTeam": "AAA", "AwayTeam": "BBB", "ForecastDescription": "Rain", "ForecastWindSpeed": 18, "OverUnder": 44.5}
    ])
    assert set(result["team"]) == {"AAA", "BBB"}
    assert result["betting_total_live"].eq(44.5).all()


def test_depth_chart_uses_verified_team_id_mapping():
    result = normalize_depth_charts(
        [{"TeamID": 1, "Offense": [{"TeamID": 1, "Name": "Example QB", "Position": "QB", "DepthOrder": 1}]}],
        {1: "ARI"},
    )
    assert result.loc[0, "team"] == "ARI"
    assert result.loc[0, "depth_order_live"] == 1
