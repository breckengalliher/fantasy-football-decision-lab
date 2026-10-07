"""Plain-language editorial outlooks for Start/Sit comparison cards."""

from __future__ import annotations

from collections.abc import Mapping

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
    opponent = str(row["next_opponent"])
    matchup = str(row["matchup_label"]).lower()
    trend = recent - season
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

    if trend >= 2:
        form = f"Based on his recent {recent:.1f} PPR average, he is running hotter than his season baseline, though we keep that short stretch in perspective."
    elif trend <= -2:
        form = f"His last four have cooled to {recent:.1f} PPR per game, but we do not overreact to one short stretch."
    else:
        form = f"Based on his {recent:.1f} recent average versus {season:.1f} for the season, we see a fairly steady outlook."

    matchup_text = {
        "favorable": f"We give him a small bump against {opponent}, while keeping that matchup adjustment intentionally modest.",
        "tough": f"We trim the estimate slightly against {opponent}, but not enough to erase his established production.",
    }.get(matchup, f"We view the matchup with {opponent} as neutral, so it does not move our projection much.")
    model_outlook = " ".join([opening, form, matchup_text])
    if reporting_summary and reporting_summary.strip():
        return f"{model_outlook} What we're hearing around the team: {reporting_summary.strip()}"
    return model_outlook
