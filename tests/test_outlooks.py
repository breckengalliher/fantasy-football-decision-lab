from dashboard.outlooks import JOURNALISM_AFFECTS_PROJECTION, build_player_outlook


def player(**changes):
    base = {"player": "Justin Jefferson", "season_ppr": 18.9, "recent_ppr": 21.2, "next_opponent": "DET", "matchup_label": "Favorable"}
    return {**base, **changes}


def test_close_start_outlook_is_conversational_and_cautious():
    text = build_player_outlook(player(), rank=0, total=3, spread=2.1)
    assert "slim margin" in text
    assert "lean" in text
    assert "small bump" in text


def test_sit_outlook_does_not_use_supplementary_context():
    text = build_player_outlook(player(recent_ppr=14, matchup_label="Tough"), rank=1, total=2, spread=4)
    assert "Sit" in text
    assert "cooled" in text
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
    assert with_reporting.endswith("Around the team: Local reporters expect his normal role.")
