import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from dashboard.providers.sportsdataio import SportsDataIOContext, enrich_board
from dashboard.providers.injuries import InjuryContext
from src.refresh_live_context import refresh_board

def player(points=4):
    return pd.DataFrame([dict(player_id="p1", player="Example Player", team="SEA", position="QB",
        floor_ppr=8.5, median_ppr=14.2 + (points-4)*2, ceiling_ppr=26.,
        projected_ppr=14.2 + (points-4)*2, is_roster_relevant=True,
        next_opponent="SF", recent_opportunities=8., spread_line=-1.5,
        market_passing_yards=250., market_implied_ppr=17.)])

def context(spread=-4.5, *, include_spread=True, games=True, depth=True):
    game = dict(team="SEA", provider_opponent="SF", game_status_live="Scheduled",
                provider_game_id="g1", game_updated_live="2026-10-11T12:00:00Z")
    if include_spread:
        game["spread_line_live"] = spread
    d = dict(player_key="example player", player="Example Player", team="SEA",
             depth_position_live="QB", depth_order_live=1)
    return SportsDataIOContext(pd.DataFrame(), pd.DataFrame([game]) if games else pd.DataFrame(),
        pd.DataFrame([d]) if depth else pd.DataFrame(), "2026-10-11T12:01:00Z")

@pytest.mark.parametrize("points", [4, 6])
@pytest.mark.parametrize("old", [None, -3., "legacy"])
def test_first_and_repeated_enrichment_preserves_owned_model_and_market(points, old):
    board = player(points)
    if old == "legacy":
        board["spread_line_live_x"] = -2.
        board["spread_line_live_y"] = -3.
        board["spread_line_live_x_x"] = -1.
    elif old is not None:
        board["spread_line_live"] = old
    before = board.copy(deep=True)
    first = enrich_board(board, context())
    again = enrich_board(first, context())
    assert_frame_equal(first, again)
    assert_frame_equal(board, before)
    assert first.columns.is_unique and len(first) == 1
    assert [c for c in first if c.startswith("spread_line_live")] == ["spread_line_live"]
    assert first.iloc[0].spread_line_live == -4.5
    for c in ("spread_line", "market_passing_yards", "market_implied_ppr",
              "floor_ppr", "median_ppr", "ceiling_ppr", "projected_ppr"):
        assert first.iloc[0][c] == before.iloc[0][c]

@pytest.mark.parametrize("options", [
    dict(spread=None), dict(include_spread=False), dict(games=False)])
def test_missing_current_spread_is_unknown_not_stale_fallback(options):
    board = player()
    board["spread_line_live"] = -3.
    board["spread_line_live_x"] = -2.
    board["spread_line_live_y"] = -4.
    result = enrich_board(board, context(**options))
    assert pd.isna(result.iloc[0].spread_line_live)
    assert result.iloc[0].spread_line == -1.5
    assert [c for c in result if c.startswith("spread_line_live")] == ["spread_line_live"]
    assert_frame_equal(result, enrich_board(result, context(**options)))

def test_missing_depth_cannot_retain_previous_role_under_fresh_timestamp():
    previous = enrich_board(player(), context())
    refreshed = enrich_board(previous, context(depth=False))
    assert pd.isna(refreshed.iloc[0].depth_order_live)
    assert pd.isna(refreshed.iloc[0].depth_position_live)

def test_conflicting_provider_game_keys_fail_without_multiplying_players():
    provider = context()
    provider.games.loc[1] = provider.games.iloc[0]
    provider.games.loc[1, "spread_line_live"] = 8.
    with pytest.raises(ValueError, match="duplicate context"):
        enrich_board(player(), provider)

@pytest.mark.parametrize("foreign", ["median_ppr", "market_passing_yards", "spread_line", "player_id"])
def test_provider_cannot_take_ownership_of_other_fields(foreign):
    provider = context()
    provider.games[foreign] = 999
    with pytest.raises(ValueError, match="Unexpected provider game fields"):
        enrich_board(player(), provider)

@pytest.mark.parametrize("points", [4, 6])
def test_full_refresh_preserves_scoring_snapshots_and_model_policy(points):
    board = player(points).drop(columns=["market_passing_yards", "market_implied_ppr"])
    original = board.copy()
    provider = context()
    provider.market_lines.loc[0, "player_key"] = "example player"
    provider.market_lines.loc[0, "team"] = "SEA"
    provider.market_lines.loc[0, "market_passing_yards"] = 250.
    provider.market_lines.loc[0, "market_passing_tds"] = 2.
    provider.market_lines.loc[0, "market_interceptions"] = 1.
    injury = InjuryContext(pd.DataFrame(), provider.refreshed_at, "Connected", "Connected")
    for _ in range(3):
        board = refresh_board(board, provider, injury, passing_td_points=points)
    assert board.columns.is_unique and len(board) == 1
    for c in ("floor_ppr", "median_ppr", "ceiling_ppr", "projected_ppr", "player_id"):
        assert board.iloc[0][c] == original.iloc[0][c]
    assert board.iloc[0].market_implied_ppr == 250/25 + 2*points - 2
    assert board.iloc[0].spread_line_live == -4.5


def test_transient_market_failure_preserves_validated_market_and_original_check_time():
    from dataclasses import replace
    board = player()
    board["market_checked_at"] = "2026-10-10T10:00:00Z"
    provider = replace(context(), market_status="Temporarily unavailable · last validated market snapshot retained")
    injury = InjuryContext(pd.DataFrame(), provider.refreshed_at, "Connected", "Connected")
    result = refresh_board(board, provider, injury)
    for column in ("market_passing_yards", "market_implied_ppr", "market_checked_at"):
        assert result.iloc[0][column] == board.iloc[0][column]

