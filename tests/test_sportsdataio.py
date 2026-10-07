from datetime import datetime, timezone

import pandas as pd

from dashboard.providers.sportsdataio import canonical_injury_status, context_freshness, format_injury_context, normalize_depth_charts, normalize_games, normalize_injuries


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
