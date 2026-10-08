import pandas as pd

from dashboard.presentation import comparison_summary, eligible_positions, filter_player_search, matchup_summary, role_summary, selection_availability_summary, team_logo_url, weather_summary


def test_flex_includes_only_rb_wr_and_te():
    assert eligible_positions("FLEX") == ("RB", "WR", "TE")
    assert eligible_positions("QB") == ("QB",)


def test_context_summaries_are_brief_and_explanatory():
    row = {
        "schedule_adjusted_index": .8,
        "latest_snap_pct": .86,
        "recent_snap_pct": .81,
        "weather_summary_live": "Clear Sky",
        "temperature_live": 88,
        "wind_live": 3,
    }
    assert matchup_summary(row) == "20% tougher than baseline"
    assert role_summary(row) == "86% snaps · role expanding"
    assert weather_summary(row) == "Clear Sky · 88°F · calm wind"


def test_comparison_summary_calls_out_a_toss_up():
    frame = pd.DataFrame([
        {"player": "JSN", "median_ppr": 21.6},
        {"player": "Lamb", "median_ppr": 21.3},
    ])
    assert comparison_summary(frame) == "JSN is the preferred start, 0.3 PPR ahead of Lamb. This is a genuine toss-up."


def test_team_logo_url_is_restricted_to_known_nfl_teams():
    assert team_logo_url("SEA") == "https://a.espncdn.com/i/teamlogos/nfl/500/sea.png"
    assert team_logo_url("WAS").endswith("/wsh.png")
    assert team_logo_url("LA").endswith("/lar.png")
    assert team_logo_url("NOT_A_TEAM") is None


def test_player_search_matches_name_or_team_and_caps_results():
    pool = pd.DataFrame([
        {"player": "CeeDee Lamb", "team": "DAL", "projected_ppr": 20},
        {"player": "Dak Prescott", "team": "DAL", "projected_ppr": 18},
        {"player": "Nico Collins", "team": "HOU", "projected_ppr": 17},
    ])
    assert filter_player_search(pool, "ceedee")["player"].tolist() == ["CeeDee Lamb"]
    assert filter_player_search(pool, "dal", limit=1)["player"].tolist() == ["CeeDee Lamb"]


def test_selection_availability_omits_source_and_raw_timestamp():
    assert selection_availability_summary({
        "injury_status_live": "Questionable",
        "practice_status_live": "Limited Participation in Practice",
        "injury_updated_live": 1791397259531,
        "injury_source_live": "Sleeper daily fallback",
    }) == "Questionable · Limited practice"
