"""Dashboard data access with an explicit demo fallback."""

from __future__ import annotations

from datetime import date
import numpy as np
import pandas as pd
from pathlib import Path

RECENT_PPR_WEIGHT = 0.10
SEASON_PPR_WEIGHT = 0.90
MATCHUP_STRENGTH = 0.25
CALIBRATED_INTERVAL_OFFSETS = {
    "QB": (-6.74, 6.17),
    "RB": (-5.69, 5.65),
    "WR": (-6.07, 4.95),
    "TE": (-4.15, 4.31),
}

DEMO_PLAYERS = pd.DataFrame(
    [
        {
            "player": "Demo RB Alpha",
            "position": "RB",
            "team": "ATL",
            "projected_points": 287.4,
            "floor": 245.0,
            "ceiling": 329.0,
            "model_value": 61,
            "market_value": 52,
            "confidence": "High",
            "opportunity_score": 94,
            "efficiency_score": 86,
            "risk_score": 24,
            "target_share": 0.13,
            "air_yard_share": 0.01,
            "red_zone_share": 0.61,
            "weekly_projection": 18.2,
            "opponent": "CAR",
            "matchup": "Favorable",
        },
        {
            "player": "Demo WR Bravo",
            "position": "WR",
            "team": "CIN",
            "projected_points": 301.8,
            "floor": 256.0,
            "ceiling": 348.0,
            "model_value": 58,
            "market_value": 62,
            "confidence": "High",
            "opportunity_score": 96,
            "efficiency_score": 91,
            "risk_score": 18,
            "target_share": 0.29,
            "air_yard_share": 0.38,
            "red_zone_share": 0.31,
            "weekly_projection": 19.4,
            "opponent": "CLE",
            "matchup": "Neutral",
        },
        {
            "player": "Demo WR Charlie",
            "position": "WR",
            "team": "SEA",
            "projected_points": 252.6,
            "floor": 208.0,
            "ceiling": 302.0,
            "model_value": 42,
            "market_value": 31,
            "confidence": "Medium",
            "opportunity_score": 88,
            "efficiency_score": 83,
            "risk_score": 36,
            "target_share": 0.25,
            "air_yard_share": 0.36,
            "red_zone_share": 0.22,
            "weekly_projection": 16.8,
            "opponent": "LAR",
            "matchup": "Favorable",
        },
        {
            "player": "Demo RB Delta",
            "position": "RB",
            "team": "MIA",
            "projected_points": 241.3,
            "floor": 192.0,
            "ceiling": 295.0,
            "model_value": 39,
            "market_value": 44,
            "confidence": "Medium",
            "opportunity_score": 82,
            "efficiency_score": 95,
            "risk_score": 48,
            "target_share": 0.11,
            "air_yard_share": -0.01,
            "red_zone_share": 0.44,
            "weekly_projection": 15.1,
            "opponent": "BUF",
            "matchup": "Difficult",
        },
        {
            "player": "Demo TE Echo",
            "position": "TE",
            "team": "ARI",
            "projected_points": 216.7,
            "floor": 183.0,
            "ceiling": 255.0,
            "model_value": 31,
            "market_value": 25,
            "confidence": "High",
            "opportunity_score": 89,
            "efficiency_score": 88,
            "risk_score": 22,
            "target_share": 0.23,
            "air_yard_share": 0.21,
            "red_zone_share": 0.28,
            "weekly_projection": 14.0,
            "opponent": "SF",
            "matchup": "Neutral",
        },
        {
            "player": "Demo QB Foxtrot",
            "position": "QB",
            "team": "BUF",
            "projected_points": 438.2,
            "floor": 385.0,
            "ceiling": 492.0,
            "model_value": 37,
            "market_value": 34,
            "confidence": "High",
            "opportunity_score": 92,
            "efficiency_score": 93,
            "risk_score": 20,
            "target_share": 0.0,
            "air_yard_share": 0.0,
            "red_zone_share": 0.71,
            "weekly_projection": 27.1,
            "opponent": "NYJ",
            "matchup": "Neutral",
        },
        {
            "player": "Demo RB Golf",
            "position": "RB",
            "team": "DEN",
            "projected_points": 198.5,
            "floor": 151.0,
            "ceiling": 249.0,
            "model_value": 22,
            "market_value": 14,
            "confidence": "Low",
            "opportunity_score": 76,
            "efficiency_score": 79,
            "risk_score": 57,
            "target_share": 0.08,
            "air_yard_share": 0.0,
            "red_zone_share": 0.39,
            "weekly_projection": 13.2,
            "opponent": "LV",
            "matchup": "Favorable",
        },
        {
            "player": "Demo DST Hotel",
            "position": "DST",
            "team": "PHI",
            "projected_points": 142.0,
            "floor": 106.0,
            "ceiling": 178.0,
            "model_value": 4,
            "market_value": 2,
            "confidence": "Medium",
            "opportunity_score": 85,
            "efficiency_score": 87,
            "risk_score": 31,
            "target_share": 0.0,
            "air_yard_share": 0.0,
            "red_zone_share": 0.0,
            "weekly_projection": 9.3,
            "opponent": "NYG",
            "matchup": "Favorable",
        },
    ]
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_BOARD_PATH = PROJECT_ROOT / "data" / "processed" / "draft_board_2026_current.csv"
RECENT_GAMES_PATH = PROJECT_ROOT / "data" / "processed" / "recent_games_2026.csv"
DEFAULT_MARKET_PATH = (
    PROJECT_ROOT / "data" / "external" / "espn_2026_ppr_12_team_auction.csv"
)

PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_player/"
    "stats_player_week_{season}.parquet"
)
SCHEDULES_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
)
SNAP_COUNTS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/"
    "snap_counts_{season}.parquet"
)
TEAM_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/stats_team/"
    "stats_team_week_{season}.parquet"
)


def current_nfl_season(today: date | None = None) -> int:
    """Return the season in progress; the NFL season changes in September."""
    today = today or date.today()
    return today.year if today.month >= 9 else today.year - 1


def load_live_weekly_data(season: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load current weekly player stats and schedules from nflverse releases."""
    season = season or current_nfl_season()
    stats = pd.read_parquet(PLAYER_STATS_URL.format(season=season))
    games = pd.read_csv(SCHEDULES_URL, low_memory=False)
    stats = stats.loc[stats["season"].eq(season)].copy()
    games = games.loc[games["season"].eq(season)].copy()
    if "season_type" in stats:
        stats = stats.loc[stats["season_type"].eq("REG")]
    if "game_type" in games:
        games = games.loc[games["game_type"].eq("REG")]
    if stats.empty:
        raise ValueError(f"nflverse has no weekly player data for {season} yet.")
    return stats, games


def load_live_context_data(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load nflverse participation and team-volume context for the selected season."""
    snaps = pd.read_parquet(SNAP_COUNTS_URL.format(season=season))
    team_stats = pd.read_parquet(TEAM_STATS_URL.format(season=season))
    return snaps, team_stats


def add_live_supplementary_context(
    board: pd.DataFrame, snaps: pd.DataFrame, team_stats: pd.DataFrame
) -> pd.DataFrame:
    """Attach live snap and pace context without changing the model projection."""
    result = board.copy()
    snap_data = snaps.loc[snaps["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    snap_data["player_key"] = snap_data["player"].astype(str).str.strip().str.casefold()
    snap_data = snap_data.sort_values(["player_key", "team", "week"])
    snap_data["recent_snap_pct"] = snap_data.groupby(["player_key", "team"])["offense_pct"].transform(
        lambda values: values.rolling(3, min_periods=1).mean()
    )
    latest_snaps = snap_data.groupby(["player_key", "team"], as_index=False).tail(1)
    latest_snaps = latest_snaps[["player_key", "team", "week", "offense_pct", "recent_snap_pct"]].rename(
        columns={"week": "snap_week", "offense_pct": "latest_snap_pct"}
    )
    result["player_key"] = result["player"].astype(str).str.strip().str.casefold()
    result = result.merge(latest_snaps, on=["player_key", "team"], how="left").drop(columns="player_key")

    teams = team_stats.copy()
    if "season_type" in teams:
        teams = teams.loc[teams["season_type"].eq("REG")]
    for column in ["attempts", "carries", "sacks_suffered"]:
        teams[column] = pd.to_numeric(teams.get(column, 0), errors="coerce").fillna(0)
    teams["offensive_plays"] = teams["attempts"] + teams["carries"] + teams["sacks_suffered"]
    teams = teams.sort_values(["team", "week"])
    teams["recent_plays"] = teams.groupby("team")["offensive_plays"].transform(
        lambda values: values.rolling(3, min_periods=1).mean()
    )
    latest_teams = teams.groupby("team", as_index=False).tail(1)[["team", "recent_plays"]]
    result = result.merge(latest_teams.rename(columns={"recent_plays": "team_recent_plays"}), on="team", how="left")
    result = result.merge(
        latest_teams.rename(columns={"team": "next_opponent", "recent_plays": "opponent_recent_plays"}),
        on="next_opponent",
        how="left",
    )
    result["combined_recent_plays"] = result["team_recent_plays"] + result["opponent_recent_plays"]
    league_game_plays = 2 * latest_teams["recent_plays"].mean()
    result["pace_index"] = result["combined_recent_plays"] / league_game_plays
    result["pace_label"] = pd.cut(
        result["pace_index"],
        bins=[-np.inf, .97, 1.03, np.inf],
        labels=["Slower", "Neutral", "Faster"],
    )
    return result


def _position_fantasy_points(frame: pd.DataFrame) -> pd.Series:
    if "fantasy_points_ppr" in frame:
        return pd.to_numeric(frame["fantasy_points_ppr"], errors="coerce")
    columns = {
        "receptions": 1.0,
        "receiving_yards": 0.1,
        "receiving_tds": 6.0,
        "rushing_yards": 0.1,
        "rushing_tds": 6.0,
        "passing_yards": 0.04,
        "passing_tds": 4.0,
        "interceptions": -2.0,
        "rushing_fumbles_lost": -2.0,
        "receiving_fumbles_lost": -2.0,
    }
    result = pd.Series(0.0, index=frame.index)
    for column, weight in columns.items():
        if column in frame:
            result += pd.to_numeric(frame[column], errors="coerce").fillna(0) * weight
    return result


def build_start_sit_board(
    weekly: pd.DataFrame, schedules: pd.DataFrame, season: int
) -> tuple[pd.DataFrame, int]:
    """Create transparent current-form, matchup, and projection signals."""
    data = weekly.copy()
    data["fantasy_points_ppr"] = _position_fantasy_points(data)
    data = data.loc[data["position"].isin(["QB", "RB", "WR", "TE"])]
    data = data.loc[data["fantasy_points_ppr"].notna()]
    completed_week = int(data["week"].max())

    player_col = "player_display_name" if "player_display_name" in data else "player_name"
    id_col = "player_id" if "player_id" in data else player_col
    team_col = "recent_team" if "recent_team" in data else "team"
    data = data.sort_values([id_col, "week"])
    data["recent_ppr"] = data.groupby(id_col)["fantasy_points_ppr"].transform(
        lambda values: values.rolling(4, min_periods=1).mean()
    )
    data["season_ppr"] = data.groupby(id_col)["fantasy_points_ppr"].transform("mean")
    data["games_played"] = data.groupby(id_col)["fantasy_points_ppr"].transform("count")
    data["historical_floor"] = data.groupby(id_col)["fantasy_points_ppr"].transform(
        lambda values: values.quantile(.20)
    )
    data["historical_median"] = data.groupby(id_col)["fantasy_points_ppr"].transform("median")
    data["historical_ceiling"] = data.groupby(id_col)["fantasy_points_ppr"].transform(
        lambda values: values.quantile(.80)
    )
    for column in ["carries", "targets", "attempts", "passing_yards", "rushing_yards", "receiving_yards", "receptions", "passing_tds", "rushing_tds", "receiving_tds"]:
        if column not in data:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
        data[f"ytd_{column}"] = data.groupby(id_col)[column].transform("sum")
    data["opportunities"] = np.select(
        [data["position"].eq("QB")],
        [data["attempts"] + data["carries"]],
        default=data["carries"] + data["targets"],
    )
    data["recent_opportunities"] = data.groupby(id_col)["opportunities"].transform(
        lambda values: values.rolling(3, min_periods=1).mean()
    )
    data["performance_residual"] = data["fantasy_points_ppr"] - data["season_ppr"]

    defense = (
        data.groupby(["opponent_team", "position"], as_index=False)
        .agg(points_allowed=("fantasy_points_ppr", "mean"), samples=("fantasy_points_ppr", "size"))
    )
    league = data.groupby("position", as_index=False)["fantasy_points_ppr"].mean().rename(
        columns={"fantasy_points_ppr": "league_position_ppr"}
    )
    defense = defense.merge(league, on="position", how="left")
    defense["matchup_index"] = (defense["points_allowed"] / defense["league_position_ppr"]).clip(.85, 1.15)
    adjusted_defense = (
        data.groupby(["opponent_team", "position"], as_index=False)["performance_residual"]
        .mean()
        .rename(columns={"performance_residual": "schedule_adjusted_residual"})
    )
    defense = defense.merge(adjusted_defense, on=["opponent_team", "position"], how="left")
    defense["schedule_adjusted_index"] = (
        1 + defense["schedule_adjusted_residual"] / defense["league_position_ppr"]
    ).clip(.80, 1.20)

    future = schedules.loc[schedules["week"].gt(completed_week)].sort_values("week")
    next_week = int(future["week"].min()) if not future.empty else completed_week
    next_games = future.loc[future["week"].eq(next_week)]
    game_context = [column for column in ["total_line", "spread_line", "gameday", "weekday", "gametime", "location", "roof", "surface", "temp", "wind"] if column in next_games]
    home = next_games[["home_team", "away_team"] + game_context].rename(columns={"home_team": team_col, "away_team": "next_opponent"})
    away = next_games[["away_team", "home_team"] + game_context].rename(columns={"away_team": team_col, "home_team": "next_opponent"})
    home["venue"] = "Home"
    away["venue"] = "Away"
    opponents = pd.concat([home, away], ignore_index=True)

    latest = data.groupby(id_col, as_index=False).tail(1).copy()
    latest = latest.merge(opponents, on=team_col, how="left")
    latest = latest.merge(
        defense.rename(columns={"opponent_team": "next_opponent"}),
        on=["next_opponent", "position"],
        how="left",
    )
    latest["matchup_index"] = latest["matchup_index"].fillna(1.0)
    latest["form_blend"] = RECENT_PPR_WEIGHT * latest["recent_ppr"] + SEASON_PPR_WEIGHT * latest["season_ppr"]
    latest["projected_ppr"] = latest["form_blend"] * (1 + MATCHUP_STRENGTH * (latest["matchup_index"] - 1))
    floor_offset = latest["position"].map({key: value[0] for key, value in CALIBRATED_INTERVAL_OFFSETS.items()})
    ceiling_offset = latest["position"].map({key: value[1] for key, value in CALIBRATED_INTERVAL_OFFSETS.items()})
    latest["floor_ppr"] = (latest["projected_ppr"] + floor_offset).clip(lower=0)
    latest["median_ppr"] = latest["projected_ppr"]
    latest["ceiling_ppr"] = latest["projected_ppr"] + ceiling_offset
    latest["trend"] = latest["recent_ppr"] - latest["season_ppr"]
    latest["matchup_label"] = pd.cut(
        latest["matchup_index"],
        bins=[-np.inf, .94, 1.06, np.inf],
        labels=["Tough", "Neutral", "Favorable"],
    )
    latest["confidence"] = np.select(
        [latest["games_played"].ge(5) & latest["samples"].fillna(0).ge(20), latest["games_played"].ge(3)],
        ["High", "Medium"],
        default="Low",
    )
    relevance_floor = latest["position"].map({"QB": 12.0, "RB": 5.0, "WR": 3.0, "TE": 2.0})
    latest["is_roster_relevant"] = (
        latest[id_col].notna()
        & latest["games_played"].ge(2)
        & latest["recent_opportunities"].ge(relevance_floor)
        & latest["fantasy_points_ppr"].notna()
    )
    latest = latest.rename(columns={player_col: "player", team_col: "team"})
    keep = [id_col, "player", "position", "team", "next_opponent", "venue", "games_played", "season_ppr", "recent_ppr", "trend", "recent_opportunities", "ytd_attempts", "ytd_carries", "ytd_targets", "ytd_passing_yards", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_receptions", "ytd_passing_tds", "ytd_rushing_tds", "ytd_receiving_tds", "points_allowed", "matchup_index", "matchup_label", "schedule_adjusted_residual", "schedule_adjusted_index", "projected_ppr", "floor_ppr", "median_ppr", "ceiling_ppr", "confidence", "is_roster_relevant"] + game_context
    keep = list(dict.fromkeys(column for column in keep if column in latest.columns))
    return latest[keep].sort_values("projected_ppr", ascending=False), next_week


def add_injury_context(players: pd.DataFrame) -> pd.DataFrame:
    """Make missing injury coverage explicit without inferring players are healthy."""
    result = players.copy()
    result["injury_status"] = "Unavailable"
    result["injury_detail"] = "No reviewed 2026 injury feed"
    result["injury_as_of"] = pd.NA
    return result


def load_dashboard_players() -> tuple[pd.DataFrame, str]:
    """Load the pipeline output, falling back visibly when it is unavailable."""
    if REAL_BOARD_PATH.exists():
        frame = add_injury_context(pd.read_csv(REAL_BOARD_PATH))
        if DEFAULT_MARKET_PATH.exists():
            frame, matched = apply_market_values(
                frame,
                pd.read_csv(DEFAULT_MARKET_PATH),
                source_label="ESPN PPR calibrated to 12 teams (Aug 9, 2026)",
                unmatched_value=float("nan"),
                unmatched_source="No ESPN 12-team match",
            )
            return frame, f"Historical model + {matched} ESPN 12-team matches"
        return frame, "Historical model"
    return add_injury_context(DEMO_PLAYERS), "Illustrative fallback"


def apply_market_values(
    players: pd.DataFrame,
    market_values: pd.DataFrame,
    source_label: str = "Uploaded 2026 market file",
    unmatched_value: float | None = None,
    unmatched_source: str | None = None,
) -> tuple[pd.DataFrame, int]:
    """Apply reviewed player auction values using exact normalized names."""
    required = {"player", "market_value", "season"}
    missing = required.difference(market_values.columns)
    if missing:
        raise ValueError("Market file is missing: " + ", ".join(sorted(missing)))
    market = market_values[list(required)].copy()
    market["season"] = pd.to_numeric(market["season"], errors="raise")
    if not market["season"].eq(2026).all():
        raise ValueError("Market file must contain only 2026 values.")
    market["player_key"] = market["player"].astype(str).str.strip().str.casefold()
    if market["player_key"].duplicated().any():
        raise ValueError("Market file contains duplicate player names.")
    market["market_value"] = pd.to_numeric(market["market_value"], errors="raise")
    if market["market_value"].lt(0).any():
        raise ValueError("Market values cannot be negative.")

    result = players.copy()
    if "comparison_source" not in result:
        result["comparison_source"] = "Internal baseline"
    result["market_value"] = pd.to_numeric(
        result["market_value"], errors="raise"
    ).astype(float)
    result["player_key"] = result["player"].astype(str).str.strip().str.casefold()
    incoming = market.set_index("player_key")["market_value"]
    matched = result["player_key"].isin(incoming.index)
    if unmatched_value is not None:
        result.loc[~matched, "market_value"] = unmatched_value
    if unmatched_source is not None:
        result.loc[~matched, "comparison_source"] = unmatched_source
    result.loc[matched, "market_value"] = result.loc[matched, "player_key"].map(incoming)
    result.loc[matched, "comparison_source"] = source_label
    return result.drop(columns="player_key"), int(matched.sum())


def prepare_draft_board(players: pd.DataFrame) -> pd.DataFrame:
    """Add portfolio-facing draft signals."""

    board = players.copy()
    if "comparison_source" not in board:
        board["comparison_source"] = "Illustrative comparison"
    board["auction_edge"] = board["model_value"] - board["market_value"]
    board["value_signal"] = pd.cut(
        board["auction_edge"],
        bins=[float("-inf"), -4, 3, float("inf")],
        labels=["Overpriced", "Fair", "Target"],
    )
    return board.sort_values(["auction_edge", "projected_points"], ascending=[False, False])


def player_history(player_name: str, players: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return actual recent games when available, otherwise demo history."""

    if RECENT_GAMES_PATH.exists() and players is not None:
        history = pd.read_csv(RECENT_GAMES_PATH)
        selected = history.loc[history["player"].eq(player_name)].copy()
        if not selected.empty:
            return selected[
                [
                    "game",
                    "opponent_team",
                    "ppr_points",
                    "target_share",
                    "air_yard_share",
                    "targets",
                    "carries",
                ]
            ]

    source = DEMO_PLAYERS if players is None else players
    player_index = source.index[source["player"].eq(player_name)][0]
    base_projection = source.loc[player_index, "weekly_projection"]
    multipliers = [0.76, 1.05, 0.89, 1.18, 0.97]
    target_share = source.loc[player_index, "target_share"]
    air_yard_share = source.loc[player_index, "air_yard_share"]
    return pd.DataFrame(
        {
            "game": ["Game -5", "Game -4", "Game -3", "Game -2", "Game -1"],
            "ppr_points": [round(base_projection * value, 1) for value in multipliers],
            "target_share": [
                max(0.0, round(target_share * value, 3)) for value in [0.91, 1.08, 0.95, 1.11, 0.98]
            ],
            "air_yard_share": [
                round(air_yard_share * value, 3) for value in [0.82, 1.17, 0.88, 1.21, 0.96]
            ],
        }
    )
