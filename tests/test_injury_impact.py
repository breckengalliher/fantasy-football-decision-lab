import pandas as pd
import pytest

from dashboard.injury_impact import apply_injury_scenario, direct_availability_factor


def row(**changes):
    base = {
        "player": "Player A", "team": "SEA", "position": "WR", "median_ppr": 20.0,
        "floor_ppr": 12.0, "ceiling_ppr": 28.0, "recent_opportunities": 8,
        "injury_status_live": None, "practice_status_live": None, "injury_body_part_live": None,
    }
    return {**base, **changes}


def test_full_participant_without_designation_has_no_penalty():
    value = direct_availability_factor(pd.Series(row(practice_status_live="Full Participation in Practice")))
    assert value == 1.0


def test_questionable_dnp_gets_conservative_workload_scenario():
    value = direct_availability_factor(pd.Series(row(injury_status_live="Questionable", practice_status_live="Did Not Participate")))
    assert value == 0.70


def test_out_player_is_removed_and_healthy_teammate_gets_capped_boost():
    board = pd.DataFrame([
        row(player="Injured WR", injury_status_live="Out", injury_body_part_live="Hamstring"),
        row(player="Healthy WR", median_ppr=15.0, floor_ppr=9.0, ceiling_ppr=22.0, recent_opportunities=7),
    ])
    result = apply_injury_scenario(board).set_index("player")
    assert result.loc["Injured WR", "injury_adjusted_median_ppr"] == 0
    assert result.loc["Healthy WR", "injury_adjusted_median_ppr"] > 15.0
    assert result.loc["Healthy WR", "injury_teammate_boost"] <= 3.0


def test_baseline_projection_is_preserved():
    result = apply_injury_scenario(pd.DataFrame([row(injury_status_live="Questionable", practice_status_live="Limited")]))
    assert result.loc[0, "baseline_median_ppr"] == pytest.approx(20.0)
    assert result.loc[0, "median_ppr"] == pytest.approx(20.0)
