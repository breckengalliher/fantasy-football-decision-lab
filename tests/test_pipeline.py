import json
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline import allocate_auction_values, custom_fantasy_points
from src.extract_rtsports_aav import extract_aav
from src.extract_espn_cheatsheet import (
    calibrate_to_12_team_league,
    extract_top300_entries,
)
from dashboard.data import add_injury_context, apply_market_values


ROOT = Path(__file__).parents[1]


def test_six_point_passing_touchdown_scoring():
    row = pd.DataFrame(
        {
            "passing_yards": [250],
            "passing_tds": [2],
            "interceptions": [1],
            "rushing_yards": [20],
            "rushing_tds": [0],
            "receptions": [0],
            "receiving_yards": [0],
            "receiving_tds": [0],
            "passing_2pt_conversions": [0],
            "rushing_2pt_conversions": [0],
            "receiving_2pt_conversions": [0],
            "rushing_fumbles_lost": [0],
            "receiving_fumbles_lost": [0],
            "sack_fumbles_lost": [0],
            "special_teams_tds": [0],
        }
    )
    assert custom_fantasy_points(row).iloc[0] == 22


def test_auction_values_reconcile_to_offensive_budget():
    config = json.loads((ROOT / "config" / "league.json").read_text())
    players = pd.DataFrame(
        {
            "position": ["QB"] * 30 + ["RB"] * 60 + ["WR"] * 72 + ["TE"] * 30,
            "projected_points": list(range(192, 0, -1)),
        }
    )
    values = allocate_auction_values(players, config)
    assert values.ge(0).all()
    assert values.gt(0).sum() == 168
    assert values.sum() == 2366


def test_generated_board_has_current_roster_and_schedule_coverage():
    board = pd.read_csv(
        ROOT / "data" / "processed" / "draft_board_2026_current.csv"
    )
    offense = board.loc[board["position"].ne("DST")]
    assert board["player_id"].is_unique
    assert offense["roster_status"].isin(["ACT", "RES"]).all()
    assert offense["opponent"].ne("TBD").all()
    assert board["model_value"].ge(0).all()
    assert board["model_value"].sum() == 2400


def test_reviewed_market_values_match_normalized_names():
    players = pd.DataFrame(
        {"player": ["Example Player", "Other Player"], "market_value": [1, 2]}
    )
    market = pd.DataFrame(
        {"player": [" example player "], "market_value": [17], "season": [2026]}
    )
    result, matched = apply_market_values(players, market)
    assert matched == 1
    assert result.loc[0, "market_value"] == 17
    assert result.loc[1, "market_value"] == 2


def test_market_import_rejects_historical_season():
    players = pd.DataFrame({"player": ["Example Player"], "market_value": [1]})
    market = pd.DataFrame(
        {"player": ["Example Player"], "market_value": [17], "season": [2025]}
    )
    with pytest.raises(ValueError, match="2026"):
        apply_market_values(players, market)


def test_rtsports_extract_is_current_and_complete():
    source_pdf = ROOT / "work" / "rtsports_2026_aav_2026-07-25.pdf"
    if not source_pdf.exists():
        pytest.skip("Downloaded source PDF is not retained in every checkout.")
    market = extract_aav(source_pdf)
    assert len(market) >= 140
    assert market["season"].eq(2026).all()
    assert market["as_of_date"].eq("2026-07-27").all()
    assert market["player"].is_unique
    assert market["market_value"].between(1, 100).all()
    assert {"QB", "RB", "WR", "TE", "DST"}.issubset(set(market["position"]))


def test_espn_values_reconcile_to_12_team_league():
    source_pdf = ROOT / "work" / "espn_2026_ppr_top300.pdf"
    if not source_pdf.exists():
        pytest.skip("Downloaded ESPN PDF is not retained in every checkout.")
    source = extract_top300_entries(source_pdf)
    market = calibrate_to_12_team_league(source)
    assert len(source) == 300
    assert len(market) == 180
    assert market["market_value"].sum() == 2400
    assert market["market_value"].ge(1).all()
    assert market["position"].ne("K").all()
    assert market["position"].eq("DST").sum() == 12


def test_missing_injury_feed_is_never_interpreted_as_healthy():
    players = pd.DataFrame({"player": ["Example Player"]})
    result = add_injury_context(players)
    assert result.loc[0, "injury_status"] == "Unavailable"
    assert pd.isna(result.loc[0, "injury_as_of"])
    assert "No reviewed" in result.loc[0, "injury_detail"]


def test_generated_dst_model_is_complete_and_conservative():
    board = pd.read_csv(
        ROOT / "data" / "processed" / "draft_board_2026_current.csv"
    )
    defenses = board.loc[board["position"].eq("DST")]
    assert len(defenses) == 32
    assert defenses["projected_points"].notna().all()
    assert defenses["player_id"].is_unique
    assert defenses["opponent"].ne("TBD").all()
    assert defenses["model_value"].gt(0).sum() == 12
    assert defenses["model_value"].between(0, 5).all()


def test_current_depth_chart_has_useful_player_coverage():
    board = pd.read_csv(
        ROOT / "data" / "processed" / "draft_board_2026_current.csv"
    )
    offense = board.loc[board["position"].ne("DST")]
    assert offense["depth_rank"].notna().mean() >= 0.70
    assert offense.loc[offense["depth_rank"].notna(), "depth_label"].notna().all()
