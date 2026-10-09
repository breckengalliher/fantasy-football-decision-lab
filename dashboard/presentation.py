"""Plain-language summaries for supplementary player-card context."""

from __future__ import annotations

import html
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from dashboard.decision_policy import CLOSE_CALL_THRESHOLD_PPR
except ModuleNotFoundError:
    from decision_policy import CLOSE_CALL_THRESHOLD_PPR


POSITION_GROUPS = {"FLEX": ("RB", "WR", "TE"), "SUPERFLEX": ("QB", "RB", "WR", "TE")}


def player_photo_html(value: object, label: object) -> str:
    """Return a safe roster photo or an accessible initials fallback."""
    name = str(label or "Player").strip()
    initials = "".join(part[0] for part in name.split()[:2] if part)[:2].upper() or "P"
    url = "" if value is None or pd.isna(value) else str(value).strip()
    aria = html.escape(name, quote=True)
    if url.startswith("https://sleepercdn.com/content/nfl/players/") and url.endswith(".jpg"):
        return f'<span class="player-photo" role="img" aria-label="{aria} roster photo" style="background-image:url(&quot;{html.escape(url, quote=True)}&quot;)"></span>'
    return f'<span class="player-photo fallback" role="img" aria-label="No roster photo available for {aria}">{html.escape(initials)}</span>'


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


def player_card_stat_summary(row: Any) -> dict[str, str]:
    """Build a compact, position-aware season snapshot for verdict cards."""

    def number(key: str) -> float:
        value = row.get(key, 0)
        try:
            return 0.0 if value is None or pd.isna(value) else float(value)
        except (TypeError, ValueError):
            return 0.0

    games = max(0, int(number("games_played")))
    position = str(row.get("position", "")).upper()
    season_average = number("season_ppr")
    if games <= 3:
        form_label = "Season form"
        form_value = season_average
    elif games == 4 and pd.notna(row.get("last_two_ppr")):
        form_label = "Last 2 avg"
        form_value = number("last_two_ppr")
    else:
        form_label = "Recent avg"
        form_value = number("recent_ppr")

    workload_label = {
        "QB": "Recent att + car/G",
        "RB": "Recent car + tgt/G",
        "WR": "Recent targets/G",
        "TE": "Recent targets/G",
    }.get(position, "Recent opp/G")
    workload_value = number("recent_opportunities")

    if position == "QB":
        season_line = (
            f'{number("ytd_attempts"):.0f} ATT · {number("ytd_passing_yards"):.0f} PASS YDS'
            f' · {number("ytd_passing_tds"):.0f} PASS TD'
        )
    elif position == "RB":
        scrimmage_yards = number("ytd_rushing_yards") + number("ytd_receiving_yards")
        touchdowns = number("ytd_rushing_tds") + number("ytd_receiving_tds")
        season_line = (
            f'{number("ytd_carries"):.0f} CAR · {scrimmage_yards:.0f} SCRIM YDS'
            f' · {touchdowns:.0f} TD'
        )
    else:
        season_line = (
            f'{number("ytd_receptions"):.0f} REC · {number("ytd_receiving_yards"):.0f} REC YDS'
            f' · {number("ytd_receiving_tds"):.0f} REC TD'
        )

    return {
        "season_label": "Season avg",
        "season_value": f"{season_average:.1f}",
        "form_label": form_label,
        "form_value": f"{form_value:.1f}",
        "workload_label": workload_label,
        "workload_value": f"{workload_value:.1f}",
        "season_line": season_line,
        "games_label": f"{games} game{'s' if games != 1 else ''}",
    }


def opponent_position_rank(board: pd.DataFrame, row: Any) -> dict[str, Any] | None:
    """Rank the upcoming defense from toughest to easiest for a position."""
    position = str(row.get("position", "")).upper()
    opponent = str(row.get("next_opponent", "")).upper()
    required = {"position", "next_opponent", "schedule_adjusted_index"}
    if not position or not opponent or not required.issubset(board.columns):
        return None
    peers = board.loc[board["position"].astype(str).str.upper().eq(position), ["next_opponent", "schedule_adjusted_index"]].copy()
    peers["next_opponent"] = peers["next_opponent"].astype(str).str.upper()
    peers["schedule_adjusted_index"] = pd.to_numeric(peers["schedule_adjusted_index"], errors="coerce")
    peers = peers.dropna().groupby("next_opponent", as_index=False)["schedule_adjusted_index"].median()
    if peers.empty or opponent not in set(peers["next_opponent"]):
        return None
    # A lower adjusted PPR index means a stronger defense, so No. 1 is toughest.
    peers = peers.sort_values(["schedule_adjusted_index", "next_opponent"], ascending=[True, True]).reset_index(drop=True)
    # Equal opponent signals must not acquire different strength by team name.
    peers["rank"] = peers["schedule_adjusted_index"].rank(method="min", ascending=True).astype(int)
    match = peers.loc[peers["next_opponent"].eq(opponent)].iloc[0]
    rank = int(match["rank"])
    total = len(peers)
    edge_band = max(1, round(total * .31))
    if rank <= edge_band:
        tone, label = "tough", "Tough matchup"
    elif rank > total - edge_band:
        tone, label = "favorable", "Favorable matchup"
    else:
        tone, label = "neutral", "Neutral matchup"
    return {"rank": rank, "total": total, "tone": tone, "label": label, "position": position, "opponent": opponent}


def player_weekly_history(weekly: pd.DataFrame, row: Any) -> pd.DataFrame:
    """Select a player's games by stable ID, with legacy name fallback only without IDs."""
    if weekly.empty:
        return weekly.copy()
    player_id = row.get("player_id")
    if "player_id" in weekly and player_id is not None and pd.notna(player_id) and str(player_id).strip():
        games = weekly.loc[weekly["player_id"].astype(str).eq(str(player_id))].copy()
    else:
        name_column = "player_display_name" if "player_display_name" in weekly else "player_name"
        games = weekly.loc[weekly[name_column].astype(str).eq(str(row.get("player", "")))].copy()
    if "season_type" in games:
        games = games.loc[games["season_type"].eq("REG")]
    if row.get("season") is not None and "season" in games:
        games = games.loc[games["season"].eq(row["season"])]
    return games.sort_values([c for c in ("season", "week") if c in games])


def fantasy_game_log(weekly: pd.DataFrame, row: Any, passing_td_points: int = 4, limit: int = 5) -> dict[str, Any]:
    """Return a compact position-aware fantasy game log for a verdict card."""
    if weekly.empty:
        return {"headers": [], "rows": []}
    games = player_weekly_history(weekly, row)
    if games.empty:
        return {"headers": [], "rows": []}
    games["_ppr"] = pd.to_numeric(games.get("fantasy_points_ppr"), errors="coerce")
    position = str(row.get("position", "")).upper()
    if position == "QB" and passing_td_points != 4 and "passing_tds" in games:
        games["_ppr"] += (passing_td_points - 4) * pd.to_numeric(games["passing_tds"], errors="coerce").fillna(0)
    games = games.dropna(subset=["week", "_ppr"]).sort_values("week", ascending=False).head(limit)

    def n(game: Any, key: str) -> float:
        value = game.get(key, 0)
        try:
            return 0.0 if value is None or pd.isna(value) else float(value)
        except (TypeError, ValueError):
            return 0.0

    headers = ["Week", "Opp", "PPR", "Volume", "Yards", "TD"]
    rows = []
    for _, game in games.iterrows():
        opponent = str(game.get("opponent_team", "—")) if pd.notna(game.get("opponent_team")) else "—"
        if position == "QB":
            volume = f'{n(game, "completions"):.0f}/{n(game, "attempts"):.0f}'
            yards = f'{n(game, "passing_yards"):.0f} pass · {n(game, "rushing_yards"):.0f} rush'
            scores = f'{n(game, "passing_tds") + n(game, "rushing_tds"):.0f}'
        elif position == "RB":
            volume = f'{n(game, "carries"):.0f} car · {n(game, "targets"):.0f} tgt'
            yards = f'{n(game, "rushing_yards") + n(game, "receiving_yards"):.0f} scrim'
            scores = f'{n(game, "rushing_tds") + n(game, "receiving_tds"):.0f}'
        else:
            volume = f'{n(game, "receptions"):.0f}/{n(game, "targets"):.0f} rec/tgt'
            yards = f'{n(game, "receiving_yards"):.0f} rec'
            scores = f'{n(game, "receiving_tds"):.0f}'
        rows.append([f'W{int(game["week"])}', opponent, f'{float(game["_ppr"]):.1f}', volume, yards, scores])
    return {"headers": headers, "rows": rows}


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
