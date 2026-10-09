"""SportsDataIO adapter for supplementary, non-model decision context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd
import requests
try:
    from dashboard.providers.http_retry import get_with_retry
except ModuleNotFoundError:
    from providers.http_retry import get_with_retry

try:
    from dashboard.football_integrity import canonical_depth, resolved_identity
except ModuleNotFoundError:
    from football_integrity import canonical_depth, resolved_identity

try:
    from dashboard.market_expectations import devig_yes_no, normalize_market_lines
except ModuleNotFoundError:
    from market_expectations import devig_yes_no, normalize_market_lines


BASE_URL = "https://api.sportsdata.io/v3/nfl"
CONTEXT_STALE_AFTER_MINUTES = 90
PROMOTION_INTERVAL_OFFSETS = {
    "QB": (-6.74, 6.17), "RB": (-5.69, 5.65), "WR": (-6.07, 4.95), "TE": (-4.15, 4.31)
}


def canonical_team(value: Any) -> str:
    """Use nflverse's Rams identifier at provider join boundaries."""
    team = str(value).strip().upper()
    return {"LAR": "LA"}.get(team, team)


@dataclass(frozen=True)
class SportsDataIOContext:
    injuries: pd.DataFrame
    games: pd.DataFrame
    depth_charts: pd.DataFrame
    refreshed_at: str
    market_lines: pd.DataFrame = field(default_factory=pd.DataFrame)
    market_status: str = "Not requested"
    depth_source_updated_at: str | None = None
    depth_freshness_verified: bool = False


def context_freshness(
    refreshed_at: str | None,
    now: datetime | None = None,
    stale_after_minutes: int = CONTEXT_STALE_AFTER_MINUTES,
) -> tuple[int | None, bool]:
    """Return whole-minute age and whether live decision context is stale."""
    if not refreshed_at:
        return None, True
    try:
        checked = datetime.fromisoformat(str(refreshed_at).replace("Z", "+00:00"))
    except ValueError:
        return None, True
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    age_minutes = max(0, int((current - checked.astimezone(timezone.utc)).total_seconds() // 60))
    return age_minutes, age_minutes > stale_after_minutes


def _first(record: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return pd.NA


def _key(value: Any) -> str:
    return str(value).strip().casefold()


def _usable(value: Any) -> Any:
    """Reject provider placeholders that look populated but contain no information."""
    if pd.isna(value) or str(value).strip().casefold() in {"scrambled", "redacted", "unavailable"}:
        return pd.NA
    return value


def canonical_injury_status(value: Any) -> Any:
    """Normalize provider variants to the five user-facing availability labels."""
    value = _usable(value)
    if pd.isna(value):
        return pd.NA
    raw = str(value).strip()
    key = raw.casefold().replace("_", " ").replace("-", " ")
    aliases = {
        "q": "Questionable", "questionable": "Questionable",
        "d": "Doubtful", "doubtful": "Doubtful",
        "o": "Out", "out": "Out",
        "ir": "IR", "injured reserve": "IR", "reserve/injured": "IR", "reserve injured": "IR",
        "inactive": "Inactive", "inactives": "Inactive",
        "pup": "PUP", "physically unable to perform": "PUP",
    }
    return aliases.get(key, raw)


def format_injury_context(row: Any, provider_connected: bool = True) -> str:
    """Render a concise availability summary without stale-looking injury noise."""
    status = canonical_injury_status(row.get("injury_status_live"))
    practice = _usable(row.get("practice_status_live"))
    body_part = _usable(row.get("injury_body_part_live"))
    practice_key = "" if pd.isna(practice) else str(practice).strip().casefold()
    is_full = practice_key in {"full", "full participation", "full participation in practice", "fp"}

    # A full session is the useful headline. Repeating the body part makes a
    # cleared limitation read like an active restriction.
    if is_full:
        if pd.notna(status):
            return f"{status} · Full participant"
        return "Full participant"

    values = [status, practice, body_part]
    values = [str(value) for value in values if pd.notna(value)]
    if values:
        text = " · ".join(values)
        updated = _usable(row.get("injury_updated_live"))
        if pd.notna(updated):
            text += f" · updated {updated}"
        source = _usable(row.get("injury_source_live"))
        if pd.notna(source):
            text += f" · {source}"
        conflict = row.get("injury_conflict_live", False)
        if pd.notna(conflict) and bool(conflict):
            text += " · sources disagree"
        return text
    record = row.get("injury_record_live")
    if pd.notna(record) and bool(record):
        return "Provider record present · status unavailable"
    return "No injury designation" if provider_connected else "Injury sources unavailable"


class SportsDataIOClient:
    def __init__(self, api_key: str, timeout: int = 20) -> None:
        if not api_key.strip():
            raise ValueError("SportsDataIO API key is empty.")
        self.api_key = api_key.strip()
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        response = get_with_retry(
            f"{BASE_URL}/{path.lstrip('/')}",
            params={"key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def weekly_context(self, season: int, week: int) -> SportsDataIOContext:
        season_code = f"{season}REG"
        games = self._get(f"scores/json/ScoresByWeek/{season_code}/{week}")
        depth = self._get("scores/json/DepthChartsAll")
        teams = self._get("scores/json/Teams")
        team_map = {
            item.get("TeamID"): item.get("Key")
            for item in teams or []
            if item.get("TeamID") is not None and item.get("Key")
        }
        market_lines, market_status = self._market_lines(games)
        return SportsDataIOContext(
            injuries=pd.DataFrame(),
            games=normalize_games(games),
            depth_charts=normalize_depth_charts(depth, team_map),
            refreshed_at=datetime.now(timezone.utc).isoformat(),
            market_lines=market_lines,
            market_status=market_status,
        )

    def weekly_market_lines(self, season: int, week: int) -> tuple[pd.DataFrame, str, str]:
        """Fetch only the schedule and player props for a lightweight refresh."""
        games = self._get(f"scores/json/ScoresByWeek/{season}REG/{week}")
        lines, status = self._market_lines(games)
        return lines, status, datetime.now(timezone.utc).isoformat()

    def _market_lines(self, games: Any) -> tuple[pd.DataFrame, str]:
        market_records: list[dict[str, Any]] = []
        market_status = "No player props currently published"
        eligible_games = [
            item for item in games or []
            if str(item.get("Status") or "Scheduled").casefold() in {"scheduled", "pregame", "time tbd"}
        ]
        score_ids = [item.get("ScoreID") for item in eligible_games]
        temporary_errors = 0
        for score_id in dict.fromkeys(value for value in score_ids if value is not None):
            try:
                props = self._get(f"odds/json/BettingPlayerPropsByScoreID/{score_id}")
            except requests.RequestException as exc:
                if getattr(exc.response, "status_code", None) in {401, 403}:
                    market_status = "Player-prop feed is not included in the connected subscription"
                elif getattr(exc.response, "status_code", None) != 404:
                    temporary_errors += 1
                continue
            market_records.extend(flatten_player_props(props))
        market_lines = normalize_market_lines(market_records)
        if not market_lines.empty:
            market_status = f"Connected · {len(market_lines)} players with validated lines"
        elif temporary_errors:
            market_status = "Temporarily unavailable · last validated market snapshot retained"
        return market_lines, market_status


def _market_key(value: Any) -> str | None:
    text = str(value or "").casefold().replace("-", " ").replace("_", " ")
    if "reception" in text and "yard" not in text:
        return "receptions"
    if "receiv" in text and "yard" in text:
        return "receiving_yards"
    if "rush" in text and "yard" in text:
        return "rushing_yards"
    if "pass" in text and "yard" in text:
        return "passing_yards"
    if "pass" in text and ("touchdown" in text or " td" in f" {text}"):
        return "passing_tds"
    if "interception" in text:
        return "interceptions"
    if "touchdown" in text and ("anytime" in text or "score" in text):
        return "rushing_receiving_tds"
    return None


def flatten_player_props(payload: Any) -> list[dict[str, Any]]:
    """Extract only unambiguous over/under player lines from provider markets."""
    flattened: list[dict[str, Any]] = []
    for market in payload or []:
        if not isinstance(market, dict):
            continue
        descriptor = " ".join(str(market.get(key) or "") for key in ("Name", "BettingBetType", "BettingMarketType", "MarketType"))
        outcomes = market.get("BettingOutcomes") or market.get("Outcomes") or market.get("ConsensusOutcomes") or []
        if _market_key(descriptor) == "rushing_receiving_tds":
            yes = next((item for item in outcomes if isinstance(item, dict) and str(item.get("BettingOutcomeType") or item.get("OutcomeType") or item.get("Name") or "").casefold() in {"yes", "over"}), None)
            no = next((item for item in outcomes if isinstance(item, dict) and str(item.get("BettingOutcomeType") or item.get("OutcomeType") or item.get("Name") or "").casefold() in {"no", "under"}), None)
            if yes:
                probability = devig_yes_no(yes.get("PayoutAmerican") or yes.get("AmericanOdds"), (no or {}).get("PayoutAmerican") or (no or {}).get("AmericanOdds"))
                player = yes.get("PlayerName") or yes.get("ParticipantName") or market.get("PlayerName") or market.get("ParticipantName")
                team = yes.get("Team") or yes.get("TeamKey") or market.get("Team") or market.get("TeamKey")
                if probability is not None and player and team:
                    flattened.append({
                        "player": player, "team": team, "market": "rushing_receiving_tds", "line": probability,
                        "book": yes.get("SportsbookName") or "Consensus", "updated_at": yes.get("Updated") or market.get("Updated"),
                    })
            continue
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            outcome_type = str(outcome.get("BettingOutcomeType") or outcome.get("OutcomeType") or outcome.get("Name") or "")
            if outcome_type and "over" not in outcome_type.casefold() and outcome_type.casefold() not in {"yes", "o"}:
                continue
            market_key = _market_key(f"{descriptor} {outcome.get('Name') or ''}")
            player = outcome.get("PlayerName") or outcome.get("ParticipantName") or market.get("PlayerName") or market.get("ParticipantName")
            team = outcome.get("Team") or outcome.get("TeamKey") or market.get("Team") or market.get("TeamKey")
            line = outcome.get("Value") if outcome.get("Value") is not None else outcome.get("Point")
            if not market_key or not player or not team or line is None:
                continue
            book = outcome.get("SportsbookName") or outcome.get("Sportsbook") or "Consensus"
            if isinstance(book, dict):
                book = book.get("Name") or book.get("Key") or "Sportsbook"
            flattened.append({
                "player": player, "team": team, "market": market_key, "line": line,
                "book": book, "updated_at": outcome.get("Updated") or market.get("Updated"),
            })
    return flattened


def normalize_injuries(payload: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in payload or []:
        name = _first(item, "Name", "PlayerName", "Player")
        team = _first(item, "Team", "TeamKey")
        if pd.isna(name) or pd.isna(team):
            continue
        rows.append(
            {
                "player_key": _key(name),
                "team": str(team),
                "injury_record_live": True,
                "injury_status_live": canonical_injury_status(_first(item, "Status", "InjuryStatus")),
                "practice_status_live": _usable(_first(item, "Practice", "PracticeStatus")),
                "injury_body_part_live": _usable(_first(item, "BodyPart", "InjuredBodyPart")),
                "injury_note_live": _usable(_first(item, "Notes", "Note")),
                "injury_position": _first(item, "Position"),
                "injury_updated_live": _usable(_first(item, "Updated", "LastUpdated", "UpdatedDate")),
            }
        )
    return pd.DataFrame(rows)


def normalize_games(payload: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in payload or []:
        home = _first(item, "HomeTeam")
        away = _first(item, "AwayTeam")
        if pd.isna(home) or pd.isna(away):
            continue
        weather = _first(item, "ForecastDescription", "WeatherDescription")
        temperature = _first(item, "ForecastTempLow", "Temperature")
        wind = _first(item, "ForecastWindSpeed", "WindSpeed")
        total = _first(item, "OverUnder", "OverUnderDisplay")
        spread = _first(item, "PointSpread", "PointSpreadDisplay")
        for team, opponent in [(home, away), (away, home)]:
            rows.append(
                {
                    "team": canonical_team(team),
                    "provider_opponent": canonical_team(opponent),
                    "weather_summary_live": weather,
                    "temperature_live": temperature,
                    "wind_live": wind,
                    "betting_total_live": total,
                    "spread_line_live": spread,
                    "game_status_live": _first(item, "Status"),
                    "game_updated_live": _first(item, "Updated", "DateTimeUTC", "DateTime"),
                    "provider_game_id": _first(item, "GameKey", "GameID", "ScoreID"),
                }
            )
    return pd.DataFrame(rows)


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def normalize_depth_charts(
    payload: Any, team_map: dict[Any, str] | None = None
) -> pd.DataFrame:
    rows = []
    seen: set[tuple[str, str]] = set()
    for item in _walk(payload or []):
        name = _first(item, "Name", "PlayerName")
        team = _first(item, "Team", "TeamKey")
        if pd.isna(team) and team_map:
            team = team_map.get(item.get("TeamID"), pd.NA)
        if pd.isna(name) or pd.isna(team):
            continue
        pair = (_key(name), canonical_team(team))
        if pair in seen:
            continue
        seen.add(pair)
        rows.append(
            {
                "player_key": pair[0],
                "player": str(name),
                "team": pair[1],
                "depth_position_live": _first(item, "Position", "DepthChartPosition"),
                "depth_order_live": _first(item, "DepthOrder", "DepthChartOrder"),
                "provider_player_id": _first(item, "PlayerID"),
                "provider_gsis_id": _first(item, "GSISID"),
            }
        )
    return pd.DataFrame(rows)


def add_depth_chart_promotions(board: pd.DataFrame, context: SportsDataIOContext) -> pd.DataFrame:
    """Add verified offensive role players who have no current-season stat row yet."""
    if context.depth_charts.empty or context.games.empty:
        return board.copy()
    result = board.copy()
    depth = canonical_depth(context.depth_charts)
    depth["team"] = depth["team"].map(canonical_team)
    depth["depth_order_live"] = pd.to_numeric(depth["depth_order_live"], errors="coerce")
    role_limits = {"QB": 1, "RB": 2, "WR": 3, "TE": 2}
    depth = depth.loc[
        depth["depth_position_live"].isin(role_limits)
        & depth["depth_order_live"].le(depth["depth_position_live"].map(role_limits))
    ].copy()
    if depth.empty:
        return result
    existing = set(zip(result["player"].map(_key), result["team"].astype(str)))
    depth = depth.loc[
        ~depth.apply(lambda row: (row["player_key"], str(row["team"])) in existing, axis=1)
    ].merge(
        context.games[["team", "provider_opponent"]].assign(team=lambda data: data["team"].map(canonical_team), provider_opponent=lambda data: data["provider_opponent"].map(canonical_team)).drop_duplicates("team"), on="team", how="inner"
    )
    if depth.empty:
        return result

    relevant = result.get("is_roster_relevant", pd.Series(False, index=result.index)).fillna(False).astype(bool)
    position_anchor = result.loc[relevant].groupby("position")["median_ppr"].median()
    team_position_anchor = result.loc[relevant].groupby(["team", "position"])["median_ppr"].median()
    opportunity_anchor = result.loc[relevant].groupby("position")["recent_opportunities"].median()
    fallback_projection = {"QB": 17.0, "RB": 9.0, "WR": 10.0, "TE": 7.0}
    fallback_opportunities = {"QB": 31.0, "RB": 11.0, "WR": 6.0, "TE": 4.5}
    interval_scale = 1.35
    additions = []
    for _, promoted in depth.iterrows():
        position = str(promoted["depth_position_live"])
        depth_order = int(promoted["depth_order_live"])
        position_prior = float(position_anchor.get(position, fallback_projection[position]))
        team_prior = float(team_position_anchor.get((str(promoted["team"]), position), position_prior))
        role_multiplier = {1: 1.00, 2: .82, 3: .68}.get(depth_order, .60)
        role_prior = position_prior * role_multiplier
        # With no personal sample, the estimate is deliberately driven by independent priors:
        # league position (50%), this team's positional environment (30%), and verified role (20%).
        median = .50 * position_prior + .30 * team_prior + .20 * role_prior
        lower, upper = PROMOTION_INTERVAL_OFFSETS[position]
        row = {column: pd.NA for column in result.columns}
        row.update({
            "player_id": (promoted.get("canonical_player_id") or
                          (f'sportsdataio:{promoted["provider_player_id"]}' if pd.notna(promoted.get("provider_player_id")) else f'depth:{promoted["player_key"]}')),
            "player": promoted["player"],
            "position": position,
            "team": promoted["team"],
            "next_opponent": promoted["provider_opponent"],
            "venue": "Game scheduled",
            "games_played": 0,
            "season_ppr": median,
            "recent_ppr": median,
            "last_two_ppr": median,
            "trend": 0.0,
            "recent_opportunities": float(opportunity_anchor.get(position, fallback_opportunities[position])),
            "projected_ppr": median,
            "median_ppr": median,
            "floor_ppr": max(0.0, median + interval_scale * lower),
            "ceiling_ppr": median + interval_scale * upper,
            "confidence": "Limited sample",
            "limited_sample_reason": "No usable current-season workload or production history",
            "limited_sample_position_prior": position_prior,
            "limited_sample_team_prior": team_prior,
            "limited_sample_role_prior": role_prior,
            "limited_sample_prior_weights": "50% position · 30% team/position · 20% depth-chart role",
            "matchup_index": 1.0,
            "schedule_adjusted_index": 1.0,
            "matchup_label": "Neutral",
            "is_roster_relevant": True,
            "limited_sample_role": True,
        })
        for stat in (
            "ytd_attempts", "ytd_carries", "ytd_targets", "ytd_passing_yards", "ytd_rushing_yards",
            "ytd_receiving_yards", "ytd_receptions", "ytd_passing_tds", "ytd_rushing_tds", "ytd_receiving_tds",
        ):
            if stat in row:
                row[stat] = 0.0
        additions.append(row)
    result["limited_sample_role"] = result.get("limited_sample_role", False)
    return pd.concat([result, pd.DataFrame(additions)], ignore_index=True)


def enrich_board(board: pd.DataFrame, context: SportsDataIOContext) -> pd.DataFrame:
    """Join provider context without modifying any projection columns."""
    result = board.copy()
    result["player_key"] = result["player"].map(_key)
    if not context.depth_charts.empty:
        depth_columns = ["player_key", "team", "depth_position_live", "depth_order_live"]
        depth = canonical_depth(context.depth_charts)[depth_columns].copy()
        depth["team"] = depth["team"].map(canonical_team)
        result = result.merge(depth, on=["player_key", "team"], how="left")
    if not context.games.empty:
        games = context.games.copy()
        games["team"] = games["team"].map(canonical_team)
        games["provider_opponent"] = games["provider_opponent"].map(canonical_team)
        # Provider-owned fields are replaced, not repeatedly suffixed. Old
        # snapshots may already contain _x/_y artifacts from earlier refreshes.
        owned = set(games.columns) - {"team"}
        obsolete = [column for column in result.columns
                    if column in owned or any(column.startswith(name + "_")
                    and set(column[len(name):].split("_")) <= {"", "x", "y"}
                    for name in owned)]
        result = result.drop(columns=obsolete)
        if games.team.duplicated().any():
            raise ValueError("Provider returned duplicate team game context")
        result = result.merge(games, on="team", how="left")
    result["sportsdataio_refreshed_at"] = context.refreshed_at
    return result.drop(columns="player_key")
