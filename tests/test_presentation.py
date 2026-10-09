import pandas as pd

from dashboard.presentation import comparison_summary, eligible_positions, fantasy_game_log, filter_player_search, matchup_summary, opponent_position_rank, player_card_stat_summary, projected_team_total, role_summary, selection_availability_summary, team_logo_url, weather_summary


def test_flex_includes_only_rb_wr_and_te():
    assert eligible_positions("FLEX") == ("RB", "WR", "TE")
    assert eligible_positions("QB") == ("QB",)


def test_projected_team_total_uses_home_spread_convention():
    home = {"venue": "Home", "betting_total_live": 47.5, "spread_line_live": -3.5}
    away = {"venue": "Away", "betting_total_live": 47.5, "spread_line_live": -3.5}
    assert projected_team_total(home) == 25.5
    assert projected_team_total(away) == 22.0


def test_projected_team_total_falls_back_and_handles_missing_line():
    assert projected_team_total({"venue": "Home", "total_line": 44, "spread_line": 2}) == 21.0
    assert projected_team_total({"venue": "Home", "total_line": 44}) is None


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


def test_player_card_stats_use_position_aware_season_totals_and_early_form_window():
    receiver = player_card_stat_summary({
        "position": "WR", "games_played": 4, "season_ppr": 18.4, "recent_ppr": 19.1,
        "last_two_ppr": 22.5, "recent_opportunities": 10.5, "ytd_receptions": 31,
        "ytd_receiving_yards": 487, "ytd_receiving_tds": 3,
    })
    assert receiver["form_label"] == "Last 2 avg"
    assert receiver["form_value"] == "22.5"
    assert receiver["workload_label"] == "Recent targets/G"
    assert receiver["season_line"] == "31 REC · 487 REC YDS · 3 REC TD"

    back = player_card_stat_summary({
        "position": "RB", "games_played": 3, "season_ppr": 15.0,
        "recent_opportunities": 17, "ytd_carries": 44, "ytd_rushing_yards": 211,
        "ytd_receiving_yards": 72, "ytd_rushing_tds": 2, "ytd_receiving_tds": 1,
    })
    assert back["form_label"] == "Season form"
    assert back["season_line"] == "44 CAR · 283 SCRIM YDS · 3 TD"


def test_opponent_rank_uses_number_one_for_the_toughest_defense():
    board = pd.DataFrame([
        {"position": "WR", "next_opponent": "SF", "schedule_adjusted_index": .80},
        {"position": "WR", "next_opponent": "TB", "schedule_adjusted_index": 1.00},
        {"position": "WR", "next_opponent": "BUF", "schedule_adjusted_index": 1.20},
    ])
    tough = opponent_position_rank(board, {"position": "WR", "next_opponent": "SF"})
    easy = opponent_position_rank(board, {"position": "WR", "next_opponent": "BUF"})
    assert (tough["rank"], tough["tone"]) == (1, "tough")
    assert (easy["rank"], easy["tone"]) == (3, "favorable")


def test_fantasy_game_log_is_position_aware_and_recent_first():
    weekly = pd.DataFrame([
        {"player_display_name": "Test WR", "week": 1, "opponent_team": "SF", "fantasy_points_ppr": 12.5, "receptions": 5, "targets": 8, "receiving_yards": 70, "receiving_tds": 1},
        {"player_display_name": "Test WR", "week": 2, "opponent_team": "TB", "fantasy_points_ppr": 18.0, "receptions": 7, "targets": 10, "receiving_yards": 90, "receiving_tds": 1},
    ])
    log = fantasy_game_log(weekly, {"player": "Test WR", "position": "WR"})
    assert log["headers"] == ["Week", "Opp", "PPR", "Volume", "Yards", "TD"]
    assert log["rows"][0] == ["W2", "TB", "18.0", "7/10 rec/tgt", "90 rec", "1"]
