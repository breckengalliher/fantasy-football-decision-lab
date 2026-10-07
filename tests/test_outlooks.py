from dashboard.outlooks import JOURNALISM_AFFECTS_PROJECTION, build_player_outlook


def player(**changes):
    base = {"player": "Justin Jefferson", "season_ppr": 18.9, "recent_ppr": 21.2, "last_two_ppr": 22.4, "games_played": 6, "next_opponent": "DET", "matchup_label": "Favorable"}
    return {**base, **changes}


def test_close_start_outlook_is_conversational_and_cautious():
    text = build_player_outlook(player(), rank=0, total=3, spread=2.1)
    assert "slim margin" in text
    assert "lean" in text
    assert "We predict" in text
    assert "small bump" in text


def test_sit_outlook_does_not_use_supplementary_context():
    text = build_player_outlook(player(recent_ppr=14, matchup_label="Tough"), rank=1, total=2, spread=4)
    assert "sit" in text.lower()
    assert "cooled" in text
    assert "model" not in text.lower()
    assert "weather" not in text.lower()
    assert "injury" not in text.lower()


def test_reporting_is_narrative_only_and_appended_after_model_reasoning():
    assert JOURNALISM_AFFECTS_PROJECTION is False
    baseline = build_player_outlook(player(), rank=0, total=2, spread=4)
    with_reporting = build_player_outlook(
        player(), rank=0, total=2, spread=4,
        reporting_summary="Local reporters expect his normal role.",
    )
    assert with_reporting.startswith(baseline)
    assert with_reporting.endswith("What we're hearing around the team: Local reporters expect his normal role.")


def test_first_three_games_use_season_baseline_without_duplicate_comparison():
    text = build_player_outlook(player(games_played=3, season_ppr=17.4, recent_ppr=17.4), rank=0, total=2, spread=4)
    assert "Through 3 games" in text
    assert "17.4 PPR season average" in text
    assert "recent average versus" not in text


def test_fourth_game_uses_last_two_average():
    text = build_player_outlook(player(games_played=4, season_ppr=18.0, recent_ppr=18.0, last_two_ppr=22.5), rank=0, total=2, spread=4)
    assert "last two games" in text
    assert "22.5 PPR" in text
