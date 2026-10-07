from datetime import datetime, timezone

import pandas as pd

from dashboard.providers.sportsdataio import SportsDataIOContext, add_depth_chart_promotions, canonical_injury_status, context_freshness, format_injury_context, normalize_depth_charts, normalize_games, normalize_injuries


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
    assert bool(result.loc[0, "injury_record_live"])
    assert result.loc[0, "injury_status_live"] == "Questionable"
    assert result.loc[0, "practice_status_live"] == "Limited"


def test_scrambled_injury_fields_are_not_treated_as_real_coverage():
    result = normalize_injuries([
        {"Name": "Example Player", "Team": "SEA", "Status": "Scrambled", "Practice": "Scrambled"}
    ])
    assert pd.isna(result.loc[0, "injury_status_live"])
    assert pd.isna(result.loc[0, "practice_status_live"])


def test_availability_labels_are_canonical_and_display_consistently():
    aliases = {
        "questionable": "Questionable",
        "DOUBTFUL": "Doubtful",
        "O": "Out",
        "Injured Reserve": "IR",
        "Reserve/Injured": "IR",
        "inactives": "Inactive",
    }
    for raw, expected in aliases.items():
        assert canonical_injury_status(raw) == expected
        rendered = format_injury_context({
            "injury_record_live": True,
            "injury_status_live": raw,
            "practice_status_live": "Limited",
            "injury_body_part_live": "Hamstring",
            "injury_updated_live": "2026-10-11T10:00:00Z",
        })
        assert rendered.startswith(f"{expected} · Limited · Hamstring · updated ")


def test_placeholder_status_displays_as_unavailable_not_a_label():
    rendered = format_injury_context({
        "injury_record_live": True,
        "injury_status_live": "Scrambled",
        "practice_status_live": "Scrambled",
    })
    assert rendered == "Provider record present · status unavailable"


def test_full_practice_is_concise_and_omits_body_part_noise():
    rendered = format_injury_context({
        "injury_record_live": True,
        "practice_status_live": "Full Participation in Practice",
        "injury_body_part_live": "Thigh",
        "injury_source_live": "nflverse daily injury report",
    })
    assert rendered == "Full participant"


def test_no_injury_record_uses_plain_language():
    assert format_injury_context({}, provider_connected=True) == "No injury designation"


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


def test_depth_chart_promotion_adds_zero_game_player_with_limited_sample_projection():
    board = pd.DataFrame([{
        "player_id": "veteran", "player": "Veteran Receiver", "position": "WR", "team": "AAA",
        "next_opponent": "BBB", "median_ppr": 12.0, "recent_opportunities": 8.0,
        "is_roster_relevant": True,
    }])
    context = SportsDataIOContext(
        injuries=pd.DataFrame(),
        games=pd.DataFrame([{"team": "AAA", "provider_opponent": "BBB"}]),
        depth_charts=normalize_depth_charts([
            {"Name": "Veteran Receiver", "Team": "AAA", "Position": "WR", "DepthOrder": 1},
            {"Name": "Promoted Receiver", "Team": "AAA", "Position": "WR", "DepthOrder": 2},
            {"Name": "Practice Squad Receiver", "Team": "AAA", "Position": "WR", "DepthOrder": 5},
        ]),
        refreshed_at="2026-10-07T12:00:00+00:00",
    )
    result = add_depth_chart_promotions(board, context).set_index("player")
    assert "Promoted Receiver" in result.index
    assert "Practice Squad Receiver" not in result.index
    assert result.loc["Promoted Receiver", "games_played"] == 0
    assert result.loc["Promoted Receiver", "confidence"] == "Limited sample"
    assert bool(result.loc["Promoted Receiver", "is_roster_relevant"])
