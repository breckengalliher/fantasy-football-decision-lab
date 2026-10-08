"""Plain-language summaries for supplementary player-card context."""

from __future__ import annotations

from typing import Any

import pandas as pd


POSITION_GROUPS = {"FLEX": ("RB", "WR", "TE")}


def eligible_positions(selection: str) -> tuple[str, ...]:
    """Return the real roster positions allowed by a comparison tab."""
    normalized = str(selection).upper()
    return POSITION_GROUPS.get(normalized, (normalized,))


NFL_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
    "HOU", "IND", "JAX", "KC", "LV", "LAC", "LA", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
}


def team_logo_url(team: Any) -> str | None:
    abbreviation = str(team or "").strip().upper()
    if abbreviation not in NFL_TEAMS:
        return None
    logo_aliases = {"WAS": "wsh", "LA": "lar"}
    espn_abbreviation = logo_aliases.get(abbreviation, abbreviation.lower())
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{espn_abbreviation}.png"


def filter_player_search(pool: pd.DataFrame, query: str, limit: int = 8) -> pd.DataFrame:
    text = " ".join(str(query or "").casefold().split())
    if not text:
        return pool.sort_values(["projected_ppr", "player"], ascending=[False, True]).head(limit)
    player_match = pool["player"].fillna("").str.casefold().str.contains(text, regex=False)
    team_match = pool["team"].fillna("").str.casefold().str.contains(text, regex=False)
    return pool.loc[player_match | team_match].sort_values(["projected_ppr", "player"], ascending=[False, True]).head(limit)


def selection_availability_summary(row: Any) -> str:
    status = row.get("injury_status_live")
    practice = row.get("practice_status_live")
    status_text = "" if status is None or pd.isna(status) else str(status).strip()
    practice_text = "" if practice is None or pd.isna(practice) else str(practice).strip()
    if practice_text.casefold() in {"full", "full participation", "full participation in practice", "fp"}:
        practice_text = "Full participant"
    elif "limited" in practice_text.casefold():
        practice_text = "Limited practice"
    elif practice_text.casefold() in {"dnp", "did not participate", "did not participate in practice"}:
        practice_text = "Did not practice"
    values = [value for value in (status_text, practice_text) if value]
    return " · ".join(values) if values else "No injury designation"


def matchup_summary(row: Any) -> str:
    value = row.get("schedule_adjusted_index")
    if value is None or pd.isna(value):
        return "Matchup data unavailable"
    delta = (float(value) - 1) * 100
    if abs(delta) < 3:
        return "Neutral matchup overall"
    return f"{abs(delta):.0f}% {'easier' if delta > 0 else 'tougher'} than baseline"


def role_summary(row: Any) -> str:
    latest = row.get("latest_snap_pct")
    recent = row.get("recent_snap_pct")
    if latest is None or pd.isna(latest):
        return "Role data unavailable"
    if recent is None or pd.isna(recent):
        return f"{float(latest):.0%} snap share"
    change = round(float(latest) - float(recent), 3)
    direction = "role expanding" if change >= .05 else "role shrinking" if change <= -.05 else "stable role"
    return f"{float(latest):.0%} snaps · {direction}"


def weather_summary(row: Any) -> str:
    description = row.get("weather_summary_live")
    temperature = row.get("temperature_live")
    wind = row.get("wind_live")
    if description is None or pd.isna(description):
        return "Weather unavailable"
    parts = [str(description)]
    if temperature is not None and pd.notna(temperature):
        parts.append(f"{float(temperature):.0f}°F")
    if wind is not None and pd.notna(wind):
        speed = float(wind)
        parts.append("calm wind" if speed < 8 else "light wind" if speed < 15 else "strong wind")
    return " · ".join(parts)


def comparison_summary(compare: pd.DataFrame) -> str:
    if compare.empty:
        return ""
    leader = compare.iloc[0]
    if len(compare) == 1:
        return f"{leader['player']} is the only player selected."
    runner_up = compare.iloc[1]
    gap = float(leader["median_ppr"] - runner_up["median_ppr"])
    if gap < 1:
        ending = "This is a genuine toss-up."
    elif gap < 2.5:
        ending = "Treat this as a lean, not a lock."
    else:
        ending = "The model sees meaningful separation."
    return f"{leader['player']} is the preferred start, {gap:.1f} PPR ahead of {runner_up['player']}. {ending}"
