import pandas as pd

from dashboard.providers.injuries import InjuryContext
from dashboard.providers.sportsdataio import SportsDataIOContext
from src.refresh_live_context import refresh_board


def test_live_context_refresh_preserves_existing_projection_values():
    board = pd.DataFrame([{
        "player_id": "p1", "player": "Example Player", "team": "SEA", "position": "WR",
        "floor_ppr": 8.5, "median_ppr": 14.2, "ceiling_ppr": 22.1, "projected_ppr": 14.2,
        "is_roster_relevant": True, "next_opponent": "SF", "recent_opportunities": 8.0,
    }])
    provider = SportsDataIOContext(
        injuries=pd.DataFrame(),
        games=pd.DataFrame([{"team": "SEA", "provider_opponent": "SF", "weather_summary_live": "Clear"}]),
        depth_charts=pd.DataFrame(),
        refreshed_at="2026-10-07T12:00:00+00:00",
    )
    injuries = InjuryContext(
        records=pd.DataFrame(), checked_at="2026-10-07T12:00:00+00:00",
        nflverse_status="Connected", sleeper_status="Connected",
    )

    refreshed = refresh_board(board, provider, injuries).set_index("player_id")

    assert refreshed.loc["p1", "floor_ppr"] == 8.5
    assert refreshed.loc["p1", "median_ppr"] == 14.2
    assert refreshed.loc["p1", "ceiling_ppr"] == 22.1
    assert refreshed.loc["p1", "projected_ppr"] == 14.2
    assert refreshed.loc["p1", "weather_summary_live"] == "Clear"
