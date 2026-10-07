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
    """Explain the frozen model result, optionally adding narrative-only reporting."""
    name = str(row["player"])
    first_name = name.split()[0]
    season = float(row["season_ppr"])
    recent = float(row["recent_ppr"])
    opponent = str(row["next_opponent"])
    matchup = str(row["matchup_label"]).lower()
    trend = recent - season
    close = total > 1 and spread < 2.5

    if total == 1:
        opening = f"{first_name} is the only player in this comparison, so there isn't a true Start/Sit choice yet."
    elif rank == 0 and close:
        opening = f"{first_name} gets the Start label, but only by a slim margin. This is a lean—not a must-start verdict."
    elif rank == 0:
        opening = f"{first_name} is the model's preferred start in this group."
    elif close:
        opening = f"{first_name} lands on the Sit side, but the projections are close enough that this is far from an easy bench call."
    else:
        opening = f"{first_name} is the Sit in this comparison because the other option carries the stronger core projection."

    if trend >= 2:
        form = f"He has been running hotter lately at {recent:.1f} PPR per game, though recent form receives only a small weight."
    elif trend <= -2:
        form = f"His last four have cooled to {recent:.1f} PPR per game, but the model does not overreact to that short stretch."
    else:
        form = f"His recent production ({recent:.1f}) is close to his {season:.1f} season average, so the outlook is fairly steady."

    matchup_text = {
        "favorable": f"The matchup with {opponent} gives him a small bump, but that adjustment is intentionally capped.",
        "tough": f"The matchup with {opponent} trims the estimate slightly, not enough to erase his established production.",
    }.get(matchup, f"The matchup with {opponent} is treated as neutral and does not move the projection much.")
    model_outlook = " ".join([opening, form, matchup_text])
    if reporting_summary and reporting_summary.strip():
        return f"{model_outlook} Around the team: {reporting_summary.strip()}"
    return model_outlook
