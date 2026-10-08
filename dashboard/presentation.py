"""Plain-language summaries for supplementary player-card context."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from dashboard.decision_policy import CLOSE_CALL_THRESHOLD_PPR
except ModuleNotFoundError:
    from decision_policy import CLOSE_CALL_THRESHOLD_PPR


POSITION_GROUPS = {"FLEX": ("RB", "WR", "TE")}


def eligible_positions(selection: str) -> tuple[str, ...]:
    """Return the real roster positions allowed by a comparison tab."""
    normalized = str(selection).upper()
    return POSITION_GROUPS.get(normalized, (normalized,))


def projected_team_total(row: Any) -> float | None:
    """Return a team's market-implied points from the game total and home spread.

    NFL schedule and provider spread fields are expressed from the home team's
    perspective: a negative number means the home team is favored.
    """
    total = row.get("betting_total_live")
    if total is None or pd.isna(total):
        total = row.get("total_line")
    spread = row.get("spread_line_live")
    if spread is None or pd.isna(spread):
        spread = row.get("spread_line")
    venue = str(row.get("venue", "")).strip().casefold()
    if total is None or pd.isna(total) or spread is None or pd.isna(spread) or venue not in {"home", "away"}:
        return None
    total_value = float(total)
    home_spread = float(spread)
    implied = (total_value - home_spread) / 2 if venue == "home" else (total_value + home_spread) / 2
    return round(implied, 1)


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


def _injury_update_time(row: Any) -> str:
    """Describe the provider's status-change time without inventing one."""
    updated = row.get("injury_updated_live")
    checked = row.get("injury_checked_at")
    value = updated if updated is not None and not pd.isna(updated) else checked
    if value is None or pd.isna(value):
        return "Status change time unavailable"
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            numeric = float(value)
            unit = "ms" if numeric > 10_000_000_000 else "s"
            timestamp = pd.to_datetime(numeric, unit=unit, utc=True)
        else:
            timestamp = pd.to_datetime(value, utc=True)
        local = timestamp.tz_convert(ZoneInfo("America/Chicago"))
        rendered = f'{local.strftime("%b")} {local.day} · {local.strftime("%I:%M %p").lstrip("0")} CT'
    except (TypeError, ValueError, OverflowError):
        return "Status change time unavailable"
    prefix = "Changed" if updated is not None and not pd.isna(updated) else "Change time unavailable · checked"
    return f"{prefix} {rendered}"


def actionable_injury_alert(row: Any) -> dict[str, str] | None:
    """Classify injury context into a small set of user actions."""
    status = "" if row.get("injury_status_live") is None or pd.isna(row.get("injury_status_live")) else str(row.get("injury_status_live")).strip()
    practice = "" if row.get("practice_status_live") is None or pd.isna(row.get("practice_status_live")) else str(row.get("practice_status_live")).strip()
    status_key = status.casefold()
    practice_key = practice.casefold()
    teammate_effect = "" if row.get("injury_teammate_effect") is None or pd.isna(row.get("injury_teammate_effect")) else str(row.get("injury_teammate_effect")).strip()
    teammate_boost = row.get("injury_teammate_boost", 0)
    try:
        teammate_boost = float(teammate_boost) if teammate_boost is not None and not pd.isna(teammate_boost) else 0.0
    except (TypeError, ValueError):
        teammate_boost = 0.0

    changed = _injury_update_time(row)
    unavailable = {"out", "ir", "injured reserve", "inactive", "pup", "suspended"}
    did_not_practice = practice_key in {"dnp", "did not participate", "did not participate in practice"} or "did not practice" in practice_key
    limited = "limited" in practice_key
    conflict_value = row.get("injury_conflict_live", False)
    has_conflict = False if conflict_value is None or pd.isna(conflict_value) else bool(conflict_value)

    if status_key in unavailable:
        return {
            "classification": "Confirmed unavailable",
            "level": "unavailable",
            "headline": status or "Unavailable",
            "changed": changed,
            "verify": "Verify the official inactive list and choose a replacement before kickoff.",
        }
    if status_key == "doubtful" or did_not_practice or (status_key == "questionable" and limited) or has_conflict:
        detail = " · ".join(value for value in (status, "Did not practice" if did_not_practice else "Limited practice" if limited else "") if value)
        return {
            "classification": "Lineup action may be needed",
            "level": "action",
            "headline": detail or "Availability is uncertain",
            "changed": changed,
            "verify": "Verify the final practice designation and official inactives before locking the lineup.",
        }
    if status_key == "questionable" or limited:
        detail = " · ".join(value for value in (status, "Limited practice" if limited else "") if value)
        return {
            "classification": "Monitor",
            "level": "monitor",
            "headline": detail or "Practice participation is limited",
            "changed": changed,
            "verify": "Verify the next practice report and final game designation.",
        }
    if teammate_effect and teammate_boost > 0:
        return {
            "classification": "Teammate opportunity increase",
            "level": "opportunity",
            "headline": teammate_effect,
            "changed": changed,
            "verify": "Verify the injured teammate’s final status and this player’s expected role before kickoff.",
        }
    return None


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
    elif gap < CLOSE_CALL_THRESHOLD_PPR:
        ending = "Treat this as a lean, not a lock."
    else:
        ending = "The model sees meaningful separation."
    return f"{leader['player']} is the preferred start, {gap:.1f} PPR ahead of {runner_up['player']}. {ending}"
