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
QB_RANGE_CALIBRATION_PATH = Path(__file__).resolve().parents[1] / "reports" / "qb-model-calibration.json"
POSITION_RANGE_CALIBRATION_PATH = Path(__file__).resolve().parents[1] / "reports" / "projection-range-calibration.json"
PLAYER_POOL_CAPS = {"QB": 32, "RB": 64, "WR": 80, "TE": 36}

# Policy lock: observed touchdown scoring always receives the approved strong
# regression. Do not add a player-level scoring-role relaxation until a reliable
# live source supplies red-zone or goal-line opportunities (not touchdown results
# or a manually maintained share).
SCORING_ROLE_TD_EXCEPTION_ENABLED = False
SCORING_ROLE_TD_EXCEPTION_REQUIREMENT = "verified red-zone or goal-line opportunity data"

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


def load_prior_weekly_data(season: int) -> pd.DataFrame:
    """Load the previous regular season used only as the approved early-season anchor."""
    previous = season - 1
    local_parquet = PROJECT_ROOT / "data" / "raw" / f"player_stats_{previous}.parquet"
    local_csv = PROJECT_ROOT / "data" / "raw" / f"player_stats_{previous}.csv"
    if local_parquet.exists():
        data = pd.read_parquet(local_parquet)
    elif local_csv.exists():
        data = pd.read_csv(local_csv, low_memory=False)
    else:
        data = pd.read_parquet(PLAYER_STATS_URL.format(season=previous))
    if "season_type" in data:
        data = data.loc[data["season_type"].eq("REG")]
    return data.loc[data["season"].eq(previous)].copy()


def add_live_supplementary_context(
    board: pd.DataFrame, snaps: pd.DataFrame, team_stats: pd.DataFrame
) -> pd.DataFrame:
    """Attach live snap and pace context without changing the model projection."""
    result = board.copy()
    for column in (
        "projection_current_signal", "projection_history_signal", "projection_current_weight",
        "projection_base", "projection_td_adjustment", "projection_workload_signal",
        "projection_matchup_factor",
    ):
        result[column] = np.nan
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
    data["last_two_ppr"] = data.groupby(id_col)["fantasy_points_ppr"].transform(
        lambda values: values.rolling(2, min_periods=1).mean()
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

    team_records = pd.DataFrame(columns=[team_col, "team_record"])
    if {"home_score", "away_score"}.issubset(schedules.columns):
        played = schedules.loc[
            schedules["week"].le(completed_week)
            & schedules["home_score"].notna()
            & schedules["away_score"].notna()
        ].copy()
        if not played.empty:
            home_records = pd.DataFrame({
                team_col: played["home_team"],
                "wins": (played["home_score"] > played["away_score"]).astype(int),
                "losses": (played["home_score"] < played["away_score"]).astype(int),
                "ties": (played["home_score"] == played["away_score"]).astype(int),
            })
            away_records = pd.DataFrame({
                team_col: played["away_team"],
                "wins": (played["away_score"] > played["home_score"]).astype(int),
                "losses": (played["away_score"] < played["home_score"]).astype(int),
                "ties": (played["away_score"] == played["home_score"]).astype(int),
            })
            team_records = pd.concat([home_records, away_records], ignore_index=True).groupby(team_col, as_index=False)[["wins", "losses", "ties"]].sum()
            team_records["team_record"] = team_records.apply(
                lambda row: f'{int(row["wins"])}-{int(row["losses"])}' + (f'-{int(row["ties"])}' if row["ties"] else ""), axis=1
            )
            team_records = team_records[[team_col, "team_record"]]

    latest = data.groupby(id_col, as_index=False).tail(1).copy()
    latest = latest.merge(opponents, on=team_col, how="left")
    latest = latest.merge(team_records, on=team_col, how="left")
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
    keep = [id_col, "player", "position", "team", "team_record", "next_opponent", "venue", "games_played", "season_ppr", "recent_ppr", "last_two_ppr", "trend", "recent_opportunities", "ytd_attempts", "ytd_carries", "ytd_targets", "ytd_passing_yards", "ytd_rushing_yards", "ytd_receiving_yards", "ytd_receptions", "ytd_passing_tds", "ytd_rushing_tds", "ytd_receiving_tds", "points_allowed", "matchup_index", "matchup_label", "schedule_adjusted_residual", "schedule_adjusted_index", "projected_ppr", "floor_ppr", "median_ppr", "ceiling_ppr", "confidence", "is_roster_relevant"] + game_context
    keep = list(dict.fromkeys(column for column in keep if column in latest.columns))
    return latest[keep].sort_values("projected_ppr", ascending=False), next_week


def add_injury_context(players: pd.DataFrame) -> pd.DataFrame:
    """Make missing injury coverage explicit without inferring players are healthy."""
    result = players.copy()
    result["injury_status"] = "Unavailable"
    result["injury_detail"] = "No reviewed 2026 injury feed"
    result["injury_as_of"] = pd.NA
    return result


def apply_verified_starter_gate(board: pd.DataFrame) -> pd.DataFrame:
    """Require a live provider depth-chart QB1 designation for QB selection."""
    result = board.copy()
    depth_position = result.get("depth_position_live", pd.Series(pd.NA, index=result.index)).astype("string")
    depth_order = pd.to_numeric(result.get("depth_order_live", pd.Series(np.nan, index=result.index)), errors="coerce")
    result["verified_qb_starter"] = ~result["position"].eq("QB") | (depth_position.eq("QB") & depth_order.eq(1))
    result["starter_gate_reason"] = np.where(
        result["position"].ne("QB"),
        "Not applicable",
        np.where(result["verified_qb_starter"], "Verified QB1 in live depth chart", "Not verified as live QB1"),
    )
    return result


def apply_player_pool_guardrails(board: pd.DataFrame) -> pd.DataFrame:
    """Fail closed on invalid identities and retain only fantasy-relevant depth."""
    result = board.copy()
    id_column = "player_id" if "player_id" in result else "player"
    base = result.get("is_roster_relevant", pd.Series(False, index=result.index)).fillna(False).astype(bool)
    result["base_roster_relevant"] = base
    verified = result.get("verified_qb_starter", pd.Series(True, index=result.index)).fillna(False).astype(bool)
    valid = (
        result[id_column].notna()
        & result["player"].astype("string").str.strip().ne("")
        & result["team"].astype("string").str.strip().ne("")
        & result["position"].isin(PLAYER_POOL_CAPS)
        & result["next_opponent"].notna()
        & verified
    )
    result["player_pool_reason"] = np.where(base & valid, "Eligible", "Missing identity, matchup, or workload")
    candidates = result.loc[base & valid].copy()
    candidates["_name_key"] = candidates["player"].astype(str).str.strip().str.casefold()
    candidates = candidates.sort_values(
        ["position", "recent_opportunities", "season_ppr", "games_played"],
        ascending=[True, False, False, False],
    )
    duplicate_id = candidates.duplicated(id_column, keep="first")
    duplicate_name = candidates.duplicated(["_name_key", "position"], keep="first")
    duplicate_indices = candidates.index[duplicate_id | duplicate_name]
    result.loc[duplicate_indices, "player_pool_reason"] = "Duplicate player identity"
    candidates = candidates.loc[~(duplicate_id | duplicate_name)]
    candidates["_pool_rank"] = candidates.groupby("position").cumcount() + 1
    cap = candidates["position"].map(PLAYER_POOL_CAPS)
    kept_indices = candidates.index[candidates["_pool_rank"].le(cap)]
    depth_indices = candidates.index[candidates["_pool_rank"].gt(cap)]
    result.loc[depth_indices, "player_pool_reason"] = "Below fantasy-relevant position depth"
    result["is_roster_relevant"] = result.index.isin(kept_indices)
    return result


def audit_player_pool(board: pd.DataFrame) -> dict[str, object]:
    """Return deterministic publication checks for the visible player pool."""
    id_column = "player_id" if "player_id" in board else "player"
    verified = board.get("verified_qb_starter", pd.Series(True, index=board.index)).fillna(False).astype(bool)
    eligible = board.loc[board["is_roster_relevant"] & verified].copy()
    eligible["_name_key"] = eligible["player"].astype(str).str.strip().str.casefold()
    return {
        "eligible_players": int(len(eligible)),
        "eligible_by_position": {key: int(value) for key, value in eligible["position"].value_counts().to_dict().items()},
        "duplicate_player_ids": int(eligible.duplicated(id_column, keep=False).sum()),
        "duplicate_player_names_by_position": int(eligible.duplicated(["_name_key", "position"], keep=False).sum()),
        "missing_player_names": int(eligible["player"].isna().sum()),
        "missing_teams": int(eligible["team"].isna().sum()),
        "missing_opponents": int(eligible["next_opponent"].isna().sum()),
        "invalid_positions": int((~eligible["position"].isin(PLAYER_POOL_CAPS)).sum()),
    }


def apply_qb_scoring_mode(
    board: pd.DataFrame, weekly: pd.DataFrame, passing_td_points: int = 4
) -> pd.DataFrame:
    """Recalculate QB production, matchup, and calibrated ranges for 4/6-point pass TD scoring."""
    if passing_td_points not in (4, 6):
        raise ValueError("passing_td_points must be 4 or 6")
    result = board.copy()
    qbs = weekly.loc[weekly["position"].eq("QB")].copy()
    if qbs.empty:
        return result
    id_column = "player_id" if "player_id" in qbs else "player_display_name"
    qbs["passing_tds"] = pd.to_numeric(qbs.get("passing_tds", 0), errors="coerce").fillna(0)
    qbs["qb_points"] = _position_fantasy_points(qbs) + (passing_td_points - 4) * qbs["passing_tds"]
    for column in ("carries", "rushing_yards"):
        qbs[column] = pd.to_numeric(qbs.get(column, 0), errors="coerce").fillna(0)
    qbs = qbs.sort_values([id_column, "week"])
    summary = qbs.groupby(id_column, as_index=False).agg(qb_season_ppr=("qb_points", "mean"))
    recent = qbs.groupby(id_column, as_index=False).tail(4).groupby(id_column, as_index=False).agg(
        qb_recent_ppr=("qb_points", "mean"),
        qb_recent_carries=("carries", "mean"),
        qb_recent_rush_yards=("rushing_yards", "mean"),
    )
    summary = summary.merge(recent, on=id_column, validate="one_to_one")
    defense = qbs.groupby("opponent_team", as_index=False)["qb_points"].mean().rename(columns={"qb_points": "qb_points_allowed"})
    league_qb = float(qbs["qb_points"].mean())
    defense["qb_matchup_index"] = (defense["qb_points_allowed"] / league_qb).clip(.90, 1.10)

    result = result.merge(summary, on=id_column, how="left")
    result = result.merge(defense, left_on="next_opponent", right_on="opponent_team", how="left").drop(
        columns="opponent_team", errors="ignore"
    )
    mask = result["position"].eq("QB")
    result.loc[mask, "season_ppr"] = result.loc[mask, "qb_season_ppr"]
    result.loc[mask, "recent_ppr"] = result.loc[mask, "qb_recent_ppr"]
    result.loc[mask, "points_allowed"] = result.loc[mask, "qb_points_allowed"]
    result.loc[mask, "matchup_index"] = result.loc[mask, "qb_matchup_index"].fillna(1.0)
    form = RECENT_PPR_WEIGHT * result.loc[mask, "recent_ppr"] + SEASON_PPR_WEIGHT * result.loc[mask, "season_ppr"]
    projection = form * (1 + MATCHUP_STRENGTH * (result.loc[mask, "matchup_index"] - 1))
    result.loc[mask, "projected_ppr"] = projection
    result.loc[mask, "median_ppr"] = projection

    # Use the validated format-specific empirical QB ranges when available.
    if QB_RANGE_CALIBRATION_PATH.exists():
        import json

        calibration = json.loads(QB_RANGE_CALIBRATION_PATH.read_text(encoding="utf-8"))
        offsets = calibration["formats"][f"{passing_td_points}_point_passing_td"]["range_offsets"]
        offset_table = {row["archetype"]: row for row in offsets}
        archetype = np.where(
            result.loc[mask, "qb_recent_carries"].ge(5) | result.loc[mask, "qb_recent_rush_yards"].ge(30),
            "Mobile",
            "Pocket",
        )
        result.loc[mask, "qb_archetype"] = archetype
        lower = pd.Series(archetype, index=result.index[mask]).map(
            {key: value["q10"] * value["lower_scale"] for key, value in offset_table.items()}
        )
        upper = pd.Series(archetype, index=result.index[mask]).map(
            {key: value["q90"] * value["upper_scale"] for key, value in offset_table.items()}
        )
        result.loc[mask, "floor_ppr"] = (projection + lower).clip(lower=0)
        result.loc[mask, "ceiling_ppr"] = projection + upper
    result["qb_passing_td_points"] = passing_td_points
    return result.drop(
        columns=["qb_season_ppr", "qb_recent_ppr", "qb_recent_carries", "qb_recent_rush_yards", "qb_points_allowed", "qb_matchup_index"],
        errors="ignore",
    )


def apply_approved_projection_model(
    board: pd.DataFrame,
    weekly: pd.DataFrame,
    prior_weekly: pd.DataFrame,
    next_week: int,
    passing_td_points: int = 4,
) -> pd.DataFrame:
    """Apply the approved round-three median and calibrated outcome ranges live."""
    if SCORING_ROLE_TD_EXCEPTION_ENABLED:
        raise RuntimeError(
            "Scoring-role touchdown exception is policy-locked until reliable "
            f"{SCORING_ROLE_TD_EXCEPTION_REQUIREMENT} is integrated and validated."
        )
    if passing_td_points not in (4, 6):
        raise ValueError("passing_td_points must be 4 or 6")
    import json

    result = board.copy()
    current = weekly.copy()
    prior = prior_weekly.copy()
    if "season_type" in current:
        current = current.loc[current["season_type"].eq("REG")]
    if "season_type" in prior:
        prior = prior.loc[prior["season_type"].eq("REG")]
    player_column = "player_id" if "player_id" in current else "player_display_name"
    team_column = "recent_team" if "recent_team" in current else "team"
    positions = ["QB", "RB", "WR", "TE"]
    current = current.loc[current["position"].isin(positions)].copy()
    prior = prior.loc[prior["position"].isin(positions)].copy()
    for frame in (current, prior):
        for column in (
            "attempts", "carries", "targets", "passing_tds", "rushing_tds", "receiving_tds",
            "passing_interceptions", "fumbles_lost_total", "rushing_yards",
        ):
            if column not in frame:
                frame[column] = 0.0
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
        frame["base_ppr"] = _position_fantasy_points(frame)
        frame["opportunities"] = np.where(
            frame["position"].eq("QB"), frame["attempts"] + frame["carries"], frame["carries"] + frame["targets"]
        )
        frame["td_points"] = 4 * frame["passing_tds"] + 6 * frame["rushing_tds"] + 6 * frame["receiving_tds"]
        non_qb = frame["position"].ne("QB")
        frame_team_column = "recent_team" if "recent_team" in frame else "team"
        team_total = frame.loc[non_qb].groupby(["season", "week", frame_team_column])["opportunities"].transform("sum")
        frame["opportunity_share"] = np.nan
        frame.loc[non_qb, "opportunity_share"] = frame.loc[non_qb, "opportunities"] / team_total.replace(0, np.nan)

    # Approved RB/WR/TE model: workload-supported production, strong TD regression,
    # steady historical fade, and a sample-scaled matchup adjustment.
    skill_current = current.loc[current["position"].ne("QB")].sort_values([player_column, "week"])
    skill_prior = prior.loc[prior["position"].ne("QB")].copy()
    skill = skill_current.groupby([player_column, "position"], as_index=False).agg(
        approved_games=("base_ppr", "size"), approved_season_ppr=("base_ppr", "mean"),
        approved_season_td=("td_points", "mean"),
    )
    recent_skill = skill_current.groupby([player_column, "position"], as_index=False).tail(3).groupby(
        [player_column, "position"], as_index=False
    ).agg(approved_recent_ppr=("base_ppr", "mean"), approved_recent_opp=("opportunities", "mean"), approved_recent_share=("opportunity_share", "mean"))
    skill = skill.merge(recent_skill, on=[player_column, "position"])
    current_rates = skill_current.groupby("position").agg(points=("base_ppr", "sum"), td=("td_points", "sum"), opp=("opportunities", "sum"))
    current_rates["ppr_rate"] = current_rates["points"] / current_rates["opp"]
    current_rates["td_rate"] = current_rates["td"] / current_rates["opp"]
    prior_anchor = skill_prior.groupby([player_column, "position"], as_index=False).agg(
        prior_ppr=("base_ppr", "mean"), prior_td=("td_points", "mean"),
        prior_opp=("opportunities", "mean"), prior_share=("opportunity_share", "mean"),
    )
    prior_rates = skill_prior.groupby("position").agg(td=("td_points", "sum"), opp=("opportunities", "sum"))
    prior_rates["td_rate"] = prior_rates["td"] / prior_rates["opp"]
    skill = skill.merge(prior_anchor, on=[player_column, "position"], how="left")
    expected_td = skill["approved_recent_opp"] * skill["position"].map(current_rates["td_rate"])
    td_regressed = skill["approved_season_ppr"] - skill["approved_season_td"] + .25 * skill["approved_season_td"] + .75 * expected_td
    workload = skill["approved_recent_opp"] * skill["position"].map(current_rates["ppr_rate"])
    skill["current_signal"] = .75 * td_regressed + .25 * workload
    prior_expected_td = skill["prior_opp"] * skill["position"].map(prior_rates["td_rate"])
    skill["history_signal"] = skill["prior_ppr"] - skill["prior_td"] + .25 * skill["prior_td"] + .75 * prior_expected_td
    skill["history_signal"] = skill["history_signal"].fillna(workload)
    weight = pd.Series(np.select(
        [skill["approved_games"].le(2), skill["approved_games"].le(6), skill["approved_games"].le(10)],
        [.40, .60, .75], default=.90,
    ), index=skill.index)
    role_change = (
        skill["approved_games"].ge(5) & skill["prior_opp"].gt(0)
        & skill["approved_recent_opp"].ge(1.25 * skill["prior_opp"])
        & skill["approved_recent_share"].ge(1.15 * skill["prior_share"])
    )
    weight = (weight + .10 * role_change.astype(float)).clip(upper=.90)
    skill["approved_weight"] = weight
    skill["approved_base"] = weight * skill["current_signal"] + (1 - weight) * skill["history_signal"]
    defense = skill_current.groupby(["opponent_team", "position"], as_index=False)["base_ppr"].agg(["mean", "size"]).reset_index()
    league = skill_current.groupby("position")["base_ppr"].mean()
    defense["raw_matchup"] = (defense["mean"] / defense["position"].map(league)).clip(.90, 1.10)
    evidence_cap = min(.10, .03 + max(0, next_week - 5) * .01)
    defense["approved_matchup_factor"] = 1 + (defense["raw_matchup"] - 1).clip(-evidence_cap, evidence_cap) * (defense["size"] / 24).clip(upper=1)
    skill = skill.merge(
        result[[player_column, "next_opponent"]], on=player_column, how="left"
    ).merge(
        defense[["opponent_team", "position", "approved_matchup_factor"]],
        left_on=["next_opponent", "position"], right_on=["opponent_team", "position"], how="left",
    )
    skill["approved_projection"] = skill["approved_base"] * skill["approved_matchup_factor"].fillna(1.0)
    skill["approved_td_adjustment"] = td_regressed - skill["approved_season_ppr"]
    result = result.merge(
        skill[[player_column, "approved_season_ppr", "approved_recent_ppr", "approved_recent_opp", "approved_weight", "approved_projection", "current_signal", "history_signal", "approved_base", "approved_td_adjustment", "approved_matchup_factor"]],
        on=player_column, how="left", validate="one_to_one",
    )
    skill_mask = result["position"].ne("QB") & result["approved_projection"].notna()
    result.loc[skill_mask, "season_ppr"] = result.loc[skill_mask, "approved_season_ppr"]
    result.loc[skill_mask, "recent_ppr"] = result.loc[skill_mask, "approved_recent_ppr"]
    result.loc[skill_mask, "recent_opportunities"] = result.loc[skill_mask, "approved_recent_opp"]
    result.loc[skill_mask, "projected_ppr"] = result.loc[skill_mask, "approved_projection"]
    result.loc[skill_mask, "median_ppr"] = result.loc[skill_mask, "approved_projection"]
    result.loc[skill_mask, "projection_current_signal"] = result.loc[skill_mask, "current_signal"]
    result.loc[skill_mask, "projection_history_signal"] = result.loc[skill_mask, "history_signal"]
    result.loc[skill_mask, "projection_current_weight"] = result.loc[skill_mask, "approved_weight"]
    result.loc[skill_mask, "projection_base"] = result.loc[skill_mask, "approved_base"]
    result.loc[skill_mask, "projection_td_adjustment"] = result.loc[skill_mask, "approved_td_adjustment"]
    result.loc[skill_mask, "projection_workload_signal"] = result.loc[skill_mask, "approved_recent_opp"]
    result.loc[skill_mask, "projection_matchup_factor"] = result.loc[skill_mask, "approved_matchup_factor"].fillna(1.0)

    if POSITION_RANGE_CALIBRATION_PATH.exists():
        ranges = json.loads(POSITION_RANGE_CALIBRATION_PATH.read_text(encoding="utf-8"))["offsets"]
        range_table = pd.DataFrame(ranges)
        buckets = pd.cut(result.loc[skill_mask, "games_played"], [0, 4, 8, np.inf], labels=["2-4", "5-8", "9+"]).astype(str)
        keys = list(zip(result.loc[skill_mask, "position"], buckets))
        lower_map = {(row["position"], row["sample_bucket"]): row["p10_offset"] for row in ranges}
        upper_map = {(row["position"], row["sample_bucket"]): row["p90_offset"] for row in ranges}
        lower = pd.Series([lower_map.get(key, 0) for key in keys], index=result.index[skill_mask])
        upper = pd.Series([upper_map.get(key, 0) for key in keys], index=result.index[skill_mask])
        result.loc[skill_mask, "floor_ppr"] = (result.loc[skill_mask, "median_ppr"] + lower).clip(lower=0)
        result.loc[skill_mask, "ceiling_ppr"] = result.loc[skill_mask, "median_ppr"] + upper

    # Apply the separately approved QB scoring-format model and empirical ranges.
    result = apply_qb_scoring_mode(result, current, passing_td_points)
    qb_current = current.loc[current["position"].eq("QB")].sort_values([player_column, "week"]).copy()
    qb_prior = prior.loc[prior["position"].eq("QB")].copy()
    if not qb_current.empty:
        for frame in (qb_current, qb_prior):
            frame["qb_points"] = frame["base_ppr"] + (passing_td_points - 4) * frame["passing_tds"]
            frame["turnovers"] = frame["passing_interceptions"] + frame["fumbles_lost_total"]
        qb = qb_current.groupby(player_column, as_index=False).agg(
            qb_games=("qb_points", "size"), qb_season=("qb_points", "mean"),
            qb_pass_tds=("passing_tds", "sum"), qb_attempts=("attempts", "sum"),
            qb_turnovers=("turnovers", "sum"),
        )
        qb_recent = qb_current.groupby(player_column, as_index=False).tail(3).groupby(player_column, as_index=False).agg(
            qb_recent_attempts=("attempts", "mean"), qb_recent_carries=("carries", "mean"),
            qb_recent_rush_yards=("rushing_yards", "mean"), qb_recent_points=("qb_points", "mean"),
        )
        qb = qb.merge(qb_recent, on=player_column)
        qb_anchor = qb_prior.groupby(player_column, as_index=False).agg(
            qb_prior_games=("qb_points", "size"), qb_prior_points=("qb_points", "mean"),
            qb_prior_tds=("passing_tds", "sum"), qb_prior_attempts=("attempts", "sum"),
            qb_prior_turnovers=("turnovers", "sum"),
        )
        qb_anchor["qb_prior_td_rate"] = qb_anchor["qb_prior_tds"] / qb_anchor["qb_prior_attempts"].replace(0, np.nan)
        qb_anchor["qb_prior_turnover_rate"] = qb_anchor["qb_prior_turnovers"] / qb_anchor["qb_prior_attempts"].replace(0, np.nan)
        qb = qb.merge(qb_anchor, on=player_column, how="left")
        observed_td_points = passing_td_points * qb["qb_pass_tds"] / qb["qb_games"]
        observed_turnover_penalty = -2 * qb["qb_turnovers"] / qb["qb_games"]
        core = qb["qb_season"] - observed_td_points - observed_turnover_penalty
        league_td_rate = qb_current["passing_tds"].sum() / qb_current["attempts"].sum()
        league_turnover_rate = qb_current["turnovers"].sum() / qb_current["attempts"].sum()
        td_rate = .50 * qb["qb_prior_td_rate"].fillna(league_td_rate) + .50 * league_td_rate
        turnover_rate = .50 * qb["qb_prior_turnover_rate"].fillna(league_turnover_rate) + .50 * league_turnover_rate
        td_signal = .25 * observed_td_points + .75 * passing_td_points * qb["qb_recent_attempts"] * td_rate
        turnover_signal = .50 * observed_turnover_penalty + .50 * -2 * qb["qb_recent_attempts"] * turnover_rate
        qb["qb_current_signal"] = core + td_signal + turnover_signal
        league_points_per_attempt = qb_current["qb_points"].sum() / qb_current["attempts"].sum()
        role_anchor = qb["qb_recent_attempts"] * league_points_per_attempt
        qb["qb_history_signal"] = qb["qb_prior_points"].where(qb["qb_prior_games"].ge(5), role_anchor)
        qb_weight = pd.Series(np.select(
            [qb["qb_games"].le(2), qb["qb_games"].le(6), qb["qb_games"].le(10)],
            [.40, .60, .75], default=.90,
        ), index=qb.index)
        qb["qb_weight"] = qb_weight
        qb["qb_base"] = qb_weight * qb["qb_current_signal"] + (1 - qb_weight) * qb["qb_history_signal"]
        qb_defense = qb_current.groupby("opponent_team", as_index=False)["qb_points"].agg(["mean", "size"]).reset_index()
        qb_defense["qb_factor"] = (qb_defense["mean"] / qb_current["qb_points"].mean()).clip(.90, 1.10)
        if next_week < 5:
            qb_defense["qb_factor"] = 1 + (qb_defense["qb_factor"] - 1) * (qb_defense["size"] / 16).clip(upper=1)
        qb = qb.merge(result[[player_column, "next_opponent"]], on=player_column, how="left").merge(
            qb_defense[["opponent_team", "qb_factor"]], left_on="next_opponent", right_on="opponent_team", how="left"
        )
        qb["approved_qb_projection"] = qb["qb_base"] * qb["qb_factor"].fillna(1.0)
        qb["qb_archetype_approved"] = np.where(
            qb["qb_prior_games"].fillna(0).lt(5), "Inexperienced",
            np.where(qb["qb_recent_carries"].ge(5) | qb["qb_recent_rush_yards"].ge(30), "Mobile", "Pocket"),
        )
        qb["qb_td_adjustment"] = td_signal - observed_td_points
        result = result.merge(
            qb[[player_column, "qb_recent_points", "approved_qb_projection", "qb_archetype_approved", "qb_current_signal", "qb_history_signal", "qb_weight", "qb_base", "qb_td_adjustment", "qb_recent_attempts", "qb_factor"]],
            on=player_column, how="left", validate="one_to_one",
        )
        qb_mask = result["position"].eq("QB") & result["approved_qb_projection"].notna()
        result.loc[qb_mask, "recent_ppr"] = result.loc[qb_mask, "qb_recent_points"]
        result.loc[qb_mask, "projected_ppr"] = result.loc[qb_mask, "approved_qb_projection"]
        result.loc[qb_mask, "median_ppr"] = result.loc[qb_mask, "approved_qb_projection"]
        result.loc[qb_mask, "projection_current_signal"] = result.loc[qb_mask, "qb_current_signal"]
        result.loc[qb_mask, "projection_history_signal"] = result.loc[qb_mask, "qb_history_signal"]
        result.loc[qb_mask, "projection_current_weight"] = result.loc[qb_mask, "qb_weight"]
        result.loc[qb_mask, "projection_base"] = result.loc[qb_mask, "qb_base"]
        result.loc[qb_mask, "projection_td_adjustment"] = result.loc[qb_mask, "qb_td_adjustment"]
        result.loc[qb_mask, "projection_workload_signal"] = result.loc[qb_mask, "qb_recent_attempts"]
        result.loc[qb_mask, "projection_matchup_factor"] = result.loc[qb_mask, "qb_factor"].fillna(1.0)
        if QB_RANGE_CALIBRATION_PATH.exists():
            qb_ranges = json.loads(QB_RANGE_CALIBRATION_PATH.read_text(encoding="utf-8"))["formats"][f"{passing_td_points}_point_passing_td"]["range_offsets"]
            q10_map = {row["archetype"]: row["q10"] * row["lower_scale"] for row in qb_ranges}
            q90_map = {row["archetype"]: row["q90"] * row["upper_scale"] for row in qb_ranges}
            lower = result.loc[qb_mask, "qb_archetype_approved"].map(q10_map)
            upper = result.loc[qb_mask, "qb_archetype_approved"].map(q90_map)
            result.loc[qb_mask, "floor_ppr"] = (result.loc[qb_mask, "median_ppr"] + lower).clip(lower=0)
            result.loc[qb_mask, "ceiling_ppr"] = result.loc[qb_mask, "median_ppr"] + upper
    result["projection_model"] = "Approved round-three live model"
    result["scoring_role_td_exception_enabled"] = False
    result["scoring_role_td_exception_requirement"] = SCORING_ROLE_TD_EXCEPTION_REQUIREMENT
    return result.drop(columns=[
        "approved_season_ppr", "approved_recent_ppr", "approved_recent_opp", "approved_weight", "approved_projection",
        "current_signal", "history_signal", "approved_base", "approved_td_adjustment", "approved_matchup_factor",
        "qb_recent_points", "approved_qb_projection", "qb_archetype_approved", "qb_current_signal", "qb_history_signal",
        "qb_weight", "qb_base", "qb_td_adjustment", "qb_recent_attempts", "qb_factor",
    ], errors="ignore")


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
