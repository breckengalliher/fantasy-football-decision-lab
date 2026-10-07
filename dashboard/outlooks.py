"""Plain-language editorial outlooks for Start/Sit comparison cards."""

from __future__ import annotations

from collections.abc import Mapping
import math

JOURNALISM_AFFECTS_PROJECTION = False


def build_player_outlook(
    row: Mapping,
    rank: int,
    total: int,
    spread: float,
    reporting_summary: str | None = None,
) -> str:
    """Explain our frozen projection in an individualized editorial voice."""
    name = str(row["player"])
    first_name = name.split()[0]
    season = float(row["season_ppr"])
    recent = float(row["recent_ppr"])
    games = int(row.get("games_played", 0) or 0)
    last_two_value = row.get("last_two_ppr")
    try:
        last_two = float(last_two_value)
    except (TypeError, ValueError):
        last_two = math.nan
    opponent = str(row["next_opponent"])
    matchup = str(row["matchup_label"]).lower()
    close = total > 1 and spread < 2.5

    if total == 1:
        opening = f"We only have {first_name} in this comparison, so add another player before treating this as a true Start/Sit call."
    elif rank == 0 and close:
        opening = f"We predict {first_name} as the start, but only by a slim margin. Based on the gap, this is a lean—not a must-start call."
    elif rank == 0:
        opening = f"We predict {first_name} as the preferred start in this group."
    elif close:
        opening = f"We have {first_name} on the Sit side, but our projections are close enough that this is far from an easy bench call."
    else:
        opening = f"We would sit {first_name} in this comparison because the other option carries the stronger projection."

    if games <= 3:
        game_label = "game" if games == 1 else "games"
        form = f"Through {games} {game_label}, his {season:.1f} PPR season average is our clearest current baseline; the sample is still too small to force a short-term trend."
    elif games == 4 and not math.isnan(last_two):
        trend = last_two - season
        if trend >= 2:
            form = f"Across the last two games, he has climbed to {last_two:.1f} PPR per game compared with {season:.1f} for the season, giving us a cautiously improving read."
        elif trend <= -2:
            form = f"His last two have slipped to {last_two:.1f} PPR per game versus {season:.1f} for the season, a short dip worth watching without overreacting to it."
        else:
            form = f"His {last_two:.1f} PPR average over the last two games is close to his {season:.1f} season mark, pointing to a steady early-season role."
    else:
        trend = recent - season
        if trend >= 2:
            form = f"He has produced {recent:.1f} PPR per game over his last four, running ahead of his {season:.1f} season pace, though we keep that hot stretch in perspective."
        elif trend <= -2:
            form = f"His last four have cooled to {recent:.1f} PPR per game from a {season:.1f} season pace, but we do not overreact to one short stretch."
        else:
            form = f"His {recent:.1f} PPR average over the last four sits close to his {season:.1f} season mark, giving us a fairly steady outlook."

    matchup_text = {
        "favorable": f"We give him a small bump against {opponent}, while keeping that matchup adjustment intentionally modest.",
        "tough": f"We trim the estimate slightly against {opponent}, but not enough to erase his established production.",
    }.get(matchup, f"We view the matchup with {opponent} as neutral, so it does not move our projection much.")
    model_outlook = " ".join([opening, form, matchup_text])
    if reporting_summary and reporting_summary.strip():
        return f"{model_outlook} What we're hearing around the team: {reporting_summary.strip()}"
    return model_outlook
