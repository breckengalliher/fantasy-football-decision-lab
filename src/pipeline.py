"""Build a reproducible 2026 draft board from nflverse weekly statistics."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd


PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "player_stats/player_stats.csv"
)
ROSTER_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "rosters/roster_2026.csv"
)
SCHEDULE_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "schedules/games.csv"
)
DEPTH_CHART_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "depth_charts/depth_charts_2026.csv"
)
SEASON_WEIGHTS = {2023: 0.15, 2024: 0.30, 2025: 0.55}
TEAM_STATS_URLS = {
    season: (
        "https://github.com/nflverse/nflverse-data/releases/download/"
        f"stats_team/stats_team_week_{season}.csv"
    )
    for season in SEASON_WEIGHTS
}
POSITIONS = ("QB", "RB", "WR", "TE")
NFL_TEAMS = (
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC "
    "LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS"
).split()


def download_file(url: str, destination: Path, force: bool = False) -> None:
    """Download a source file once, preserving a reproducible local raw layer."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        return
    request = urllib.request.Request(url, headers={"User-Agent": "fantasy-portfolio/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        destination.write_bytes(response.read())


def custom_fantasy_points(frame: pd.DataFrame) -> pd.Series:
    """Apply the portfolio league's full-PPR, six-point passing-TD scoring."""
    return (
        frame["passing_yards"].fillna(0) * 0.04
        + frame["passing_tds"].fillna(0) * 6
        - frame["interceptions"].fillna(0) * 2
        + frame["rushing_yards"].fillna(0) * 0.1
        + frame["rushing_tds"].fillna(0) * 6
        + frame["receptions"].fillna(0)
        + frame["receiving_yards"].fillna(0) * 0.1
        + frame["receiving_tds"].fillna(0) * 6
        + (
            frame["passing_2pt_conversions"].fillna(0)
            + frame["rushing_2pt_conversions"].fillna(0)
            + frame["receiving_2pt_conversions"].fillna(0)
        )
        * 2
        - (
            frame["rushing_fumbles_lost"].fillna(0)
            + frame["receiving_fumbles_lost"].fillna(0)
            + frame["sack_fumbles_lost"].fillna(0)
        )
        * 2
        + frame["special_teams_tds"].fillna(0) * 6
    )


def build_player_projections(raw: pd.DataFrame) -> pd.DataFrame:
    """Create volume-adjusted 2026 estimates using 2023-2025 regular seasons."""
    data = raw.loc[
        raw["season"].isin(SEASON_WEIGHTS)
        & raw["season_type"].eq("REG")
        & raw["position"].isin(POSITIONS)
    ].copy()
    data["custom_points"] = custom_fantasy_points(data)
    data["played"] = (
        data[
            [
                "attempts",
                "carries",
                "targets",
                "receptions",
                "passing_yards",
                "rushing_yards",
                "receiving_yards",
            ]
        ]
        .fillna(0)
        .abs()
        .sum(axis=1)
        .gt(0)
    )
    data = data.loc[data["played"]]

    season = (
        data.groupby(
            ["player_id", "player_display_name", "position", "recent_team", "season"],
            as_index=False,
        )
        .agg(
            games=("week", "nunique"),
            points=("custom_points", "sum"),
            target_share=("target_share", "mean"),
            air_yard_share=("air_yards_share", "mean"),
            targets=("targets", "sum"),
            carries=("carries", "sum"),
            receptions=("receptions", "sum"),
            receiving_yards=("receiving_yards", "sum"),
            receiving_tds=("receiving_tds", "sum"),
        )
    )
    season["points_per_game"] = season["points"] / season["games"]
    season["weight"] = season["season"].map(SEASON_WEIGHTS)
    season["weighted_games"] = season["games"] * season["weight"]

    latest = (
        season.sort_values(["player_id", "season"])
        .groupby("player_id", as_index=False)
        .tail(1)[["player_id", "player_display_name", "position", "recent_team"]]
    )
    totals = (
        season.groupby("player_id", as_index=False)
        .apply(
            lambda group: pd.Series(
                {
                    "projected_ppg": np.average(
                        group["points_per_game"], weights=group["weighted_games"]
                    ),
                    "target_share": np.average(
                        group["target_share"].fillna(0), weights=group["weighted_games"]
                    ),
                    "air_yard_share": np.average(
                        group["air_yard_share"].fillna(0), weights=group["weighted_games"]
                    ),
                    "history_games": int(group["games"].sum()),
                    "seasons_used": int(group["season"].nunique()),
                    "last_season_ppg": float(
                        group.sort_values("season").iloc[-1]["points_per_game"]
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index(drop=True)
    )
    projections = latest.merge(totals, on="player_id", validate="one_to_one")
    projections["projected_points"] = projections["projected_ppg"] * 17
    projections["baseline_points"] = projections["last_season_ppg"] * 17
    projections["floor"] = projections["projected_points"] * 0.80
    projections["ceiling"] = projections["projected_points"] * 1.20
    projections["confidence"] = np.select(
        [projections["history_games"].ge(30), projections["history_games"].ge(12)],
        ["High", "Medium"],
        default="Low",
    )
    projections["risk_score"] = np.select(
        [projections["confidence"].eq("High"), projections["confidence"].eq("Medium")],
        [25, 45],
        default=70,
    )
    return projections


def replacement_levels(players: pd.DataFrame, config: dict) -> dict[str, float]:
    """Estimate replacement from the final projected draft slot by position."""
    ranks = config["auction_pool"]["projected_draft_counts"]
    levels: dict[str, float] = {}
    for position in POSITIONS:
        rank = int(ranks[position])
        pool = players.loc[players["position"].eq(position), "projected_points"].sort_values(
            ascending=False
        )
        levels[position] = float(pool.iloc[min(rank, len(pool)) - 1])
    return levels


def allocate_auction_values(
    players: pd.DataFrame,
    config: dict,
    points_column: str = "projected_points",
    dst_spend: int = 34,
) -> pd.Series:
    """Allocate an exact league budget using value over replacement.

    Players outside the projected 168-player offensive draft pool receive a $0
    recommended bid. The selected pool receives a $1 base, and all remaining
    offensive dollars are assigned with a largest-remainder allocation.
    """
    league_budget = int(config["draft"]["league_budget"])
    counts = config["auction_pool"]["projected_draft_counts"]
    scoring_frame = players.assign(projected_points=players[points_column])
    levels = replacement_levels(scoring_frame, config)
    selected_indices: list[int] = []
    for position in POSITIONS:
        eligible = scoring_frame.loc[
            scoring_frame["position"].eq(position)
            & scoring_frame["projected_points"].notna()
        ].sort_values("projected_points", ascending=False)
        selected_indices.extend(eligible.head(int(counts[position])).index.tolist())

    values = pd.Series(0, index=players.index, dtype="int64")
    values.loc[selected_indices] = 1
    offensive_base = len(selected_indices)
    discretionary = league_budget - dst_spend - offensive_base
    vorp = (
        scoring_frame.loc[selected_indices, "projected_points"]
        - scoring_frame.loc[selected_indices, "position"].map(levels)
    ).clip(lower=0)
    raw_bonus = vorp / vorp.sum() * discretionary
    floor_bonus = np.floor(raw_bonus).astype(int)
    values.loc[selected_indices] += floor_bonus
    remaining = discretionary - int(floor_bonus.sum())
    if remaining:
        fractional_order = (raw_bonus - floor_bonus).sort_values(ascending=False)
        values.loc[fractional_order.head(remaining).index] += 1
    return values


def current_roster_pool(roster: pd.DataFrame) -> pd.DataFrame:
    """Return one current 2026 roster row per fantasy-relevant player."""
    pool = roster.loc[
        roster["season"].eq(2026)
        & roster["position"].isin(POSITIONS)
        & roster["status"].isin(["ACT", "RES"])
        & roster["gsis_id"].notna()
    ].copy()
    pool["team"] = pool["team"].replace({"LA": "LAR"})
    pool = pool.sort_values(["gsis_id", "week"]).drop_duplicates("gsis_id", keep="last")
    return pool[
        ["gsis_id", "full_name", "position", "team", "status", "years_exp", "week"]
    ].rename(
        columns={
            "gsis_id": "player_id",
            "full_name": "roster_name",
            "position": "roster_position",
            "team": "roster_team",
            "status": "roster_status",
            "week": "roster_week",
        }
    )


def current_depth_chart(depth_chart: pd.DataFrame) -> pd.DataFrame:
    """Return the best current offensive depth-chart row per GSIS player ID."""
    chart = depth_chart.loc[
        depth_chart["gsis_id"].notna()
        & depth_chart["pos_abb"].isin(POSITIONS)
    ].copy()
    chart["dt"] = pd.to_datetime(chart["dt"], utc=True, errors="coerce")
    latest = chart["dt"].max()
    chart = chart.loc[chart["dt"].eq(latest)]
    chart = chart.sort_values(["gsis_id", "pos_rank", "pos_slot"]).drop_duplicates(
        "gsis_id", keep="first"
    )
    return chart[
        ["gsis_id", "pos_abb", "pos_rank", "pos_slot", "dt"]
    ].rename(
        columns={
            "gsis_id": "player_id",
            "pos_abb": "depth_position",
            "pos_rank": "depth_rank",
            "pos_slot": "depth_slot",
            "dt": "depth_chart_as_of",
        }
    )


def week_one_opponents(schedules: pd.DataFrame) -> dict[str, str]:
    """Build a team-to-opponent mapping for the 2026 regular-season opener."""
    games = schedules.loc[
        schedules["season"].eq(2026)
        & schedules["game_type"].eq("REG")
        & schedules["week"].eq(1)
    ]
    mapping: dict[str, str] = {}
    for game in games.itertuples():
        away = "LAR" if str(game.away_team) == "LA" else str(game.away_team)
        home = "LAR" if str(game.home_team) == "LA" else str(game.home_team)
        mapping[away] = home
        mapping[home] = away
    return mapping


def build_recent_games(raw: pd.DataFrame, board: pd.DataFrame) -> pd.DataFrame:
    """Return each rostered player's five most recent regular-season appearances."""
    history = raw.loc[
        raw["season"].isin(SEASON_WEIGHTS)
        & raw["season_type"].eq("REG")
        & raw["player_id"].isin(board["player_id"])
    ].copy()
    history["ppr_points"] = custom_fantasy_points(history)
    history = (
        history.sort_values(["player_id", "season", "week"])
        .groupby("player_id", as_index=False)
        .tail(5)
    )
    names = board[["player_id", "player"]].drop_duplicates("player_id")
    history = history.merge(names, on="player_id", how="left", validate="many_to_one")
    history["game"] = (
        history["season"].astype(str) + " W" + history["week"].astype(int).astype(str)
    )
    return history[
        [
            "player_id",
            "player",
            "game",
            "season",
            "week",
            "opponent_team",
            "ppr_points",
            "target_share",
            "air_yards_share",
            "targets",
            "carries",
        ]
    ].rename(columns={"air_yards_share": "air_yard_share"})


def points_allowed_score(points_allowed: pd.Series, config: dict) -> pd.Series:
    """Apply the configured ESPN-style points-allowed tiers."""
    result = pd.Series(0.0, index=points_allowed.index)
    for tier in config["team_defense_scoring"]["points_allowed"]:
        minimum = tier["minimum"]
        maximum = tier["maximum"]
        mask = points_allowed.ge(minimum)
        if maximum is not None:
            mask &= points_allowed.le(maximum)
        result.loc[mask] = tier["points"]
    return result


def dst_auction_values(projected_points: pd.Series) -> pd.Series:
    """Assign conservative $0-$5 values to exactly 12 draftable D/ST units."""
    rank = projected_points.rank(method="first", ascending=False)
    return pd.Series(
        np.select(
            [rank.eq(1), rank.le(3), rank.le(6), rank.le(12)],
            [5, 4, 3, 2],
            default=0,
        ),
        index=projected_points.index,
    )


def build_dst_projections(
    team_stats: pd.DataFrame, schedules: pd.DataFrame, config: dict
) -> pd.DataFrame:
    """Estimate 2026 D/ST scoring from 2023-2025 weekly team results."""
    stats = team_stats.loc[
        team_stats["season"].isin(SEASON_WEIGHTS)
        & team_stats["season_type"].eq("REG")
    ].copy()
    stats["team"] = stats["team"].replace({"LA": "LAR"})

    games = schedules.loc[
        schedules["season"].isin(SEASON_WEIGHTS)
        & schedules["game_type"].eq("REG")
    ]
    home = games[
        ["game_id", "season", "week", "home_team", "home_score", "away_score"]
    ].rename(
        columns={
            "home_team": "team",
            "home_score": "points_for",
            "away_score": "points_allowed_raw",
        }
    )
    away = games[
        ["game_id", "season", "week", "away_team", "away_score", "home_score"]
    ].rename(
        columns={
            "away_team": "team",
            "away_score": "points_for",
            "home_score": "points_allowed_raw",
        }
    )
    score_long = pd.concat([home, away], ignore_index=True)
    score_long["team"] = score_long["team"].replace({"LA": "LAR"})
    stats = stats.merge(
        score_long,
        on=["game_id", "season", "week", "team"],
        how="left",
        validate="one_to_one",
    )

    opponent_blocks = stats[
        ["game_id", "team", "fg_blocked", "pat_blocked", "pt_blocked"]
    ].rename(
        columns={
            "team": "opponent_team_join",
            "fg_blocked": "opponent_fg_blocked",
            "pat_blocked": "opponent_pat_blocked",
            "pt_blocked": "opponent_pt_blocked",
        }
    )
    stats["opponent_team_join"] = stats["opponent_team"].replace({"LA": "LAR"})
    stats = stats.merge(
        opponent_blocks,
        on=["game_id", "opponent_team_join"],
        how="left",
        validate="one_to_one",
    )

    scoring = config["team_defense_scoring"]
    return_tds = stats["def_tds"].fillna(0) + stats["special_teams_tds"].fillna(0)
    non_offensive_points = return_tds * scoring["interception_return_touchdown"]
    points_allowed = (stats["points_allowed_raw"] - non_offensive_points).clip(lower=0)
    blocked = (
        stats["opponent_fg_blocked"].fillna(0)
        + stats["opponent_pat_blocked"].fillna(0)
        + stats["opponent_pt_blocked"].fillna(0)
    )
    stats["dst_points"] = (
        stats["def_sacks"].fillna(0) * scoring["sack"]
        + stats["def_interceptions"].fillna(0) * scoring["interception"]
        + stats["fumble_recovery_opp"].fillna(0) * scoring["fumble_recovery"]
        + blocked * scoring["blocked_punt_pat_or_field_goal"]
        + stats["def_safeties"].fillna(0) * scoring["safety"]
        + return_tds * scoring["interception_return_touchdown"]
        + points_allowed_score(points_allowed, config)
    )

    season = (
        stats.groupby(["team", "season"], as_index=False)
        .agg(games=("game_id", "nunique"), points=("dst_points", "sum"))
    )
    season["ppg"] = season["points"] / season["games"]
    season["weight"] = season["season"].map(SEASON_WEIGHTS)
    season["weighted_games"] = season["games"] * season["weight"]
    latest_ppg = (
        season.sort_values(["team", "season"])
        .groupby("team")
        .tail(1)
        .set_index("team")["ppg"]
    )
    projection = (
        season.groupby("team")
        .apply(
            lambda group: pd.Series(
                {
                    "projected_ppg": np.average(
                        group["ppg"], weights=group["weighted_games"]
                    ),
                    "history_games": int(group["games"].sum()),
                    "seasons_used": int(group["season"].nunique()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    projection["projected_points"] = projection["projected_ppg"] * 17
    projection["baseline_points"] = projection["team"].map(latest_ppg) * 17
    projection["model_value"] = dst_auction_values(projection["projected_points"])
    projection["market_value"] = dst_auction_values(projection["baseline_points"])
    projection["comparison_source"] = "2025 production baseline"
    projection["auction_edge"] = projection["model_value"] - projection["market_value"]
    projection["value_signal"] = np.select(
        [projection["auction_edge"].gt(1), projection["auction_edge"].lt(-1)],
        ["Target", "Overpriced"],
        default="Fair",
    )
    projection["player_id"] = "DST_" + projection["team"]
    projection["player_display_name"] = projection["team"] + " D/ST"
    projection["position"] = "DST"
    projection["recent_team"] = projection["team"]
    projection["floor"] = projection["projected_points"] * 0.75
    projection["ceiling"] = projection["projected_points"] * 1.25
    projection["confidence"] = "High"
    projection["opportunity_score"] = (
        projection["projected_points"].rank(pct=True) * 100
    ).round()
    projection["efficiency_score"] = projection["opportunity_score"]
    projection["risk_score"] = 45
    projection["target_share"] = np.nan
    projection["air_yard_share"] = np.nan
    projection["red_zone_share"] = np.nan
    projection["weekly_projection"] = projection["projected_ppg"]
    opponents = week_one_opponents(schedules)
    projection["opponent"] = projection["team"].map(opponents).fillna("TBD")
    projection["matchup"] = "Unrated"
    return projection.drop(columns="team")


def build_board(
    raw: pd.DataFrame,
    config: dict,
    roster: pd.DataFrame | None = None,
    schedules: pd.DataFrame | None = None,
    team_stats: pd.DataFrame | None = None,
    depth_chart: pd.DataFrame | None = None,
) -> pd.DataFrame:
    history = build_player_projections(raw)
    if roster is None:
        players = history
        players["roster_status"] = "Unknown"
        players["years_exp"] = np.nan
        players["roster_week"] = np.nan
    else:
        players = current_roster_pool(roster).merge(
            history, on="player_id", how="left", validate="one_to_one"
        )
        players["player_display_name"] = players["roster_name"]
        players["position"] = players["roster_position"]
        players["recent_team"] = players["roster_team"]
        players["confidence"] = players["confidence"].fillna("Unavailable")
        players["risk_score"] = players["risk_score"].fillna(80)
    if depth_chart is not None:
        players = players.merge(
            current_depth_chart(depth_chart),
            on="player_id",
            how="left",
            validate="one_to_one",
        )
        players["depth_label"] = np.select(
            [players["depth_rank"].eq(1), players["depth_rank"].eq(2)],
            ["First team", "Second team"],
            default="Reserve / unlisted",
        )
    else:
        players["depth_position"] = np.nan
        players["depth_rank"] = np.nan
        players["depth_slot"] = np.nan
        players["depth_chart_as_of"] = pd.NaT
        players["depth_label"] = "Unavailable"

    players["model_value"] = allocate_auction_values(players, config)
    players["market_value"] = allocate_auction_values(
        players.rename(columns={"projected_points": "_model_points"}).rename(
            columns={"baseline_points": "projected_points"}
        ),
        config,
    )
    players["comparison_source"] = "2025 production baseline"
    players["auction_edge"] = players["model_value"] - players["market_value"]
    players["value_signal"] = np.select(
        [players["auction_edge"].gt(3), players["auction_edge"].lt(-4)],
        ["Target", "Overpriced"],
        default="Fair",
    )
    players["opportunity_score"] = (
        players.groupby("position")["projected_points"].rank(pct=True) * 100
    ).round()
    players["efficiency_score"] = (
        players.groupby("position")["projected_ppg"].rank(pct=True) * 100
    ).round()
    players["red_zone_share"] = np.nan
    players["weekly_projection"] = players["projected_ppg"]
    opponents = week_one_opponents(schedules) if schedules is not None else {}
    players["opponent"] = players["recent_team"].map(opponents).fillna("TBD")
    players["matchup"] = np.where(players["opponent"].eq("TBD"), "TBD", "Unrated")

    if team_stats is not None and schedules is not None:
        dst = build_dst_projections(team_stats, schedules, config)
    else:
        dst = pd.DataFrame(
        {
            "player_id": [f"DST_{team}" for team in NFL_TEAMS],
            "player_display_name": [f"{team} D/ST" for team in NFL_TEAMS],
            "position": "DST",
            "recent_team": NFL_TEAMS,
            "projected_points": np.nan,
            "floor": np.nan,
            "ceiling": np.nan,
            "model_value": 1,
            "market_value": 1,
            "auction_edge": 0,
            "value_signal": "Fair",
            "confidence": "Unavailable",
            "opportunity_score": np.nan,
            "efficiency_score": np.nan,
            "risk_score": 80,
            "target_share": np.nan,
            "air_yard_share": np.nan,
            "red_zone_share": np.nan,
            "weekly_projection": np.nan,
            "opponent": "TBD",
            "matchup": "Preseason",
            "history_games": 0,
            "seasons_used": 0,
        }
        )
    board = pd.concat([players, dst], ignore_index=True, sort=False)
    board = board.rename(columns={"player_display_name": "player", "recent_team": "team"})
    return board.sort_values(
        ["model_value", "projected_points"], ascending=[False, False]
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    raw_path = root / "data" / "raw" / "player_stats.csv"
    roster_path = root / "data" / "raw" / "roster_2026.csv"
    schedule_path = root / "data" / "raw" / "games.csv"
    depth_chart_path = root / "data" / "raw" / "depth_charts_2026.csv"
    team_stat_paths = {
        season: root / "data" / "raw" / f"stats_team_week_{season}.csv"
        for season in SEASON_WEIGHTS
    }
    output_path = root / "data" / "processed" / "draft_board_2026_current.csv"
    recent_path = root / "data" / "processed" / "recent_games_2026.csv"
    download_file(PLAYER_STATS_URL, raw_path, args.force_download)
    download_file(ROSTER_URL, roster_path, args.force_download)
    download_file(SCHEDULE_URL, schedule_path, args.force_download)
    download_file(DEPTH_CHART_URL, depth_chart_path, args.force_download)
    for season, url in TEAM_STATS_URLS.items():
        download_file(url, team_stat_paths[season], args.force_download)
    raw = pd.read_csv(raw_path, low_memory=False)
    roster = pd.read_csv(roster_path, low_memory=False)
    schedules = pd.read_csv(schedule_path, low_memory=False)
    depth_chart = pd.read_csv(depth_chart_path, low_memory=False)
    team_stats = pd.concat(
        [pd.read_csv(path, low_memory=False) for path in team_stat_paths.values()],
        ignore_index=True,
    )
    config = json.loads((root / "config" / "league.json").read_text())
    board = build_board(raw, config, roster, schedules, team_stats, depth_chart)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(output_path, index=False)
    recent_games = build_recent_games(raw, board)
    recent_games.to_csv(recent_path, index=False)
    print(
        f"Wrote {len(board):,} rows to {output_path}\n"
        f"Positions: {board.groupby('position').size().to_dict()}\n"
        f"Projected: {board['projected_points'].notna().sum():,}; "
        f"unavailable: {board['projected_points'].isna().sum():,}"
    )


if __name__ == "__main__":
    main()
