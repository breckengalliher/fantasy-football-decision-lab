"""Synthetic football rule fixtures, explicitly not live NFL facts."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from dashboard.data import apply_qb_scoring_mode, repair_qb_display_form
from dashboard.injury_impact import apply_injury_scenario
from dashboard.lineup_rules import build_lineup_actions, game_has_started
from dashboard.presentation import fantasy_game_log, opponent_position_rank, player_card_stat_summary
from dashboard.replacement_optimizer import optimize_replacements
from dashboard.outlooks import build_player_outlook
from dashboard.providers.sportsdataio import SportsDataIOContext, add_depth_chart_promotions, enrich_board, normalize_depth_charts, normalize_games
from src.football_qa import SCORING, independent_ppr, require_no_hard_errors, validate_assignments, validate_board, validate_weekly
from src.model_round_two import build_rows, prepare_weekly


def game(**changes):
    return {**{c: 0 for c in SCORING}, "player_id": "qb1", "player_display_name": "Fixture QB", "position": "QB", "season": 2026, "season_type": "REG", "team": "SEA", "opponent_team": "SF", "week": 1, "attempts": 30, "completions": 20, "targets": 0, "passing_yards": 250, "passing_tds": 2, "fantasy_points_ppr": 18., **changes}


def board_row(**changes):
    return {"player_id": "qb1", "player": "Fixture QB", "position": "QB", "team": "SEA", "next_opponent": "SF", "floor_ppr": 5., "median_ppr": 18., "ceiling_ppr": 30., "projected_ppr": 18., "games_played": 4, "season_ppr": 18., "recent_ppr": 18., "last_two_ppr": 18., "recent_opportunities": 30., "is_roster_relevant": True, **changes}


@pytest.mark.parametrize("points,expected", [(4, 21.), (6, 25.)])
def test_raw_scoring_all_categories_and_no_double_fumble(points, expected):
    fixture = game(receptions=2, receiving_yards=10, rushing_yards=20,
                   passing_interceptions=1, sack_fumbles_lost=1, rushing_fumbles_lost=1,
                   receiving_fumbles_lost=1, passing_2pt_conversions=1,
                   rushing_2pt_conversions=1, receiving_2pt_conversions=1,
                   fumbles_lost_total=3)
    assert independent_ppr(pd.DataFrame([fixture]), points).iloc[0] == expected


def test_incomplete_scoring_is_warning_not_false_certification():
    flags = validate_weekly(pd.DataFrame([game()]).drop(columns="special_teams_tds"))
    assert any(f.code == "incomplete_scoring" for f in flags)
    require_no_hard_errors(flags)


def test_scoring_mismatch_fails_qa():
    with pytest.raises(AssertionError, match="scoring_mismatch"):
        require_no_hard_errors(validate_weekly(pd.DataFrame([game(fantasy_points_ppr=19)])))


def test_team_td_identity_requires_complete_feed():
    data = pd.DataFrame([game()])
    assert not any(f.code == "team_td_identity" for f in validate_weekly(data))
    assert any(f.code == "team_td_identity" for f in validate_weekly(data, complete_team_feed=True))


def test_negative_yards_legal_but_completions_cannot_exceed_attempts():
    data = pd.DataFrame([game(rushing_yards=-2, fantasy_points_ppr=17.8)])
    require_no_hard_errors(validate_weekly(data))
    data.loc[0, "completions"] = 31
    with pytest.raises(AssertionError, match="count_identity"):
        require_no_hard_errors(validate_weekly(data))


def test_display_repair_does_not_change_approved_forecast_or_interval():
    board = pd.DataFrame([board_row()])
    weekly = pd.DataFrame([game(week=w, passing_tds=w, fantasy_points_ppr=10+4*w) for w in (1, 2, 3, 4)])
    result = repair_qb_display_form(board, weekly, 6)
    assert result.last_two_ppr.iloc[0] == 31
    pd.testing.assert_frame_equal(result[["median_ppr", "floor_ppr", "ceiling_ppr", "projected_ppr"]], board[["median_ppr", "floor_ppr", "ceiling_ppr", "projected_ppr"]])


def test_backup_qb_promotion_without_history_preserves_explicit_priors():
    board = pd.DataFrame([board_row(), board_row(player_id="depth:fixture", player="Promoted Fixture", games_played=0)])
    result = apply_qb_scoring_mode(board, pd.DataFrame([game(carries=2, rushing_yards=8)]), 6)
    promoted = result.loc[result.player_id.eq("depth:fixture")].iloc[0]
    assert promoted.median_ppr == 18
    assert promoted.floor_ppr == 5
    assert promoted.ceiling_ppr == 30


def test_rams_team_alias_does_not_create_a_fake_promoted_starter():
    board = pd.DataFrame([board_row(team="LA")])
    depth = normalize_depth_charts([{"Name":"Fixture QB", "Team":"LAR", "Position":"QB", "DepthOrder":1}])
    games = normalize_games([{"HomeTeam":"LAR", "AwayTeam":"BUF"}])
    context = SportsDataIOContext(pd.DataFrame(), games, depth, "2026-10-09T00:00:00Z")
    result = add_depth_chart_promotions(board, context)
    assert len(result) == 1
    enriched = enrich_board(result, context)
    assert enriched.depth_order_live.iloc[0] == 1
    assert enriched.provider_opponent.iloc[0] == "BUF"


def test_matchup_direction_ties_and_duplicate_defenses():
    board = pd.DataFrame([{"position": "WR", "next_opponent": team, "schedule_adjusted_index": index} for team,index in (("SF", .8), ("SEA", .8), ("BUF", 1.), ("LA", 1.2), ("LA", 1.2))])
    assert opponent_position_rank(board, {"position":"WR", "next_opponent":"SF"})["rank"] == 1
    assert opponent_position_rank(board, {"position":"WR", "next_opponent":"SEA"})["rank"] == 1
    easy = opponent_position_rank(board, {"position":"WR", "next_opponent":"LA"})
    assert easy["rank"] == 4 and easy["total"] == 4 and easy["tone"] == "favorable"


def test_traded_player_history_uses_id_and_retains_both_teams():
    weekly = pd.DataFrame([game(team="SEA"), game(team="LA", week=2), game(player_id="other", team="SF", week=3)])
    log = fantasy_game_log(weekly, board_row(), 6)
    assert [row[0] for row in log["rows"]] == ["W2", "W1"]
    assert log["rows"][0][2] == "22.0"


def test_zero_recent_production_is_not_missing_and_workload_is_not_touches():
    stats = player_card_stat_summary(board_row(position="RB", last_two_ppr=0))
    assert stats["form_value"] == "0.0"
    assert stats["workload_label"] == "Recent car + tgt/G"


def test_qb_injury_effect_explanation_not_erased_without_opportunity_boost():
    board = pd.DataFrame([board_row(injury_status_live="Out"), board_row(player_id="wr1", player="Fixture WR", position="WR")])
    result = apply_injury_scenario(board)
    assert result.loc[1, "injury_teammate_boost"] == 0
    assert result.loc[1, "injury_teammate_effect"]
    assert result.loc[1, "injury_adjusted_median_ppr"] < result.loc[1, "median_ppr"]


@pytest.mark.parametrize("scenario,changes", [
    ("rb_committee", {"position":"RB", "injury_status_live":"Out"}),
    ("wr1_out", {"position":"WR", "injury_status_live":"Out"}),
    ("rookie", {"position":"WR", "games_played":0, "limited_sample_role":True}),
    ("te_role_increase", {"position":"TE", "recent_opportunities":9}),
    ("inactive", {"injury_status_live":"Inactive"}),
    ("conflicting_depth", {"injury_conflict_live":True}),
])
def test_synthetic_personnel_scenarios_do_not_mutate_baseline(scenario, changes):
    source = pd.DataFrame([board_row(**changes), board_row(player_id="mate", player="Fixture Teammate", position="WR")])
    result = apply_injury_scenario(source)
    pd.testing.assert_series_equal(result.median_ppr, source.median_ppr)
    if changes.get("injury_status_live") in {"Out", "Inactive"}:
        assert result.injury_adjusted_median_ppr.iloc[0] == 0


@pytest.mark.parametrize("changes", [{"bye_week":True}, {"game_started":True}, {"data_unavailable":True}, {"availability":"Inactive"}])
def test_ineligible_bench_never_actionable(changes):
    assert not optimize_replacements([{"slot_id":"r", "slot_type":"FLEX"}], [{"player_id":"r1", "position":"RB", "median_ppr":20, **changes}])


def test_flex_superflex_global_conflict_and_roster_validation():
    slots = [{"slot_id":"f", "slot_type":"FLEX"}, {"slot_id":"s", "slot_type":"SUPERFLEX"}]
    bench = [{"player_id":"rb", "position":"RB", "median_ppr":20}, {"player_id":"qb", "position":"QB", "median_ppr":19}]
    result = optimize_replacements(slots, bench)
    assert [(r.slot_id,r.player_id) for r in result] == [("f","rb"),("s","qb")]
    require_no_hard_errors(validate_assignments([{**slots[i], "player_id":r.player_id, "position":bench[i]["position"]} for i,r in enumerate(result)]))
    with pytest.raises(AssertionError):
        require_no_hard_errors(validate_assignments([{"slot_id":"f", "slot_type":"FLEX", "player_id":"qb", "position":"QB"}]))


def test_questionable_to_inactive_mandatory_action():
    now = datetime.now(timezone.utc)
    row = {"slot_type":"WR", "player_id":"wr", "kickoff_at": now+timedelta(hours=1), "availability":"Questionable"}
    assert not build_lineup_actions([row],now)[0].mandatory
    row["availability"] = "Inactive"
    assert build_lineup_actions([row],now)[0].mandatory


def test_postponed_old_kickoff_is_not_a_locked_game():
    now = datetime.now(timezone.utc)
    player = {"player_id":"fixture", "slot_type":"QB", "kickoff_at":now-timedelta(hours=2), "game_status_live":"Postponed", "availability":"Questionable"}
    assert not game_has_started(player, now)
    assert build_lineup_actions([player],now)


def test_unavailable_player_never_receives_start_outlook():
    copy = build_player_outlook(board_row(injury_status_live="Inactive", matchup_label="Neutral"), 0, 2, 6)
    assert "Do not use this baseline" in copy
    assert "preferred start" not in copy


def test_invalid_interval_blocks_ci_but_missing_stat_forecasts_are_warning():
    with pytest.raises(AssertionError, match="invalid_interval"):
        require_no_hard_errors(validate_board(pd.DataFrame([board_row(floor_ppr=19)])))
    flags = validate_board(pd.DataFrame([board_row()]))
    assert any(f.code == "no_team_forecast_accounting" for f in flags)
    require_no_hard_errors(flags)


def test_conflicting_two_qb1_records_are_review_flags_not_fake_certainty():
    board = pd.DataFrame([board_row(verified_qb_starter=True), board_row(player_id="qb2", verified_qb_starter=True)])
    assert any(f.code == "conflicting_qb_depth" for f in validate_board(board))


def test_walk_forward_features_do_not_use_target_or_future_week_outcomes():
    data = pd.DataFrame([game(week=w, attempts=30, passing_tds=2, fantasy_points_ppr=18.) for w in range(1,6)])
    baseline = build_rows(prepare_weekly(data), round_three=True)
    mutated = data.copy()
    mutated.loc[mutated.week.ge(4), ["fantasy_points_ppr", "passing_tds", "attempts"]] = [100., 10, 60]
    changed = build_rows(prepare_weekly(mutated), round_three=True)
    fields = ["season_ppr", "recent_opportunities", "current_ppr_rate", "current_td_rate", "matchup_index", "prediction"]
    pd.testing.assert_frame_equal(baseline.loc[baseline.week.eq(4),fields].reset_index(drop=True), changed.loc[changed.week.eq(4),fields].reset_index(drop=True))
