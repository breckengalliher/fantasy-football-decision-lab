"""User-facing empty and provider-state messages."""

from __future__ import annotations


def provider_issue_message(status: str) -> str | None:
    if status.startswith("Connected"):
        return None
    if status.startswith("Connection error"):
        return (
            "Live injury, weather, odds, and depth-chart context could not be refreshed. "
            "Core projections are still available; use **Refresh now** before locking a lineup."
        )
    return (
        "Supplementary live context is not connected. Core projections are still available, "
        "but confirm injuries and official inactive lists elsewhere before kickoff."
    )


def empty_player_pool_message(position: str, hidden_qbs: int = 0) -> str:
    if position == "QB" and hidden_qbs:
        return (
            f"No verified QB1 options are available for this week. {hidden_qbs} relevant QB record(s) "
            "were withheld because the live depth chart did not confirm them as starters."
        )
    return (
        f"No eligible {position} players with an upcoming matchup are available for this week. "
        "Try another position or refresh after schedules and player records update."
    )
