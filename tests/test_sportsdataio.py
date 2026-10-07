from dashboard.providers.sportsdataio import normalize_depth_charts, normalize_games, normalize_injuries


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
