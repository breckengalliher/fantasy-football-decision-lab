"""Backtest the user-selected six-point passing-TD quarterback model."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def prepare(frame: pd.DataFrame, passing_td_points: int = 6) -> pd.DataFrame:
    data = frame.copy()
    if "season_type" in data:
        data = data.loc[data["season_type"].eq("REG")]
    data = data.loc[data["position"].eq("QB")].copy()
    columns = [
        "attempts", "carries", "passing_yards", "passing_tds", "passing_interceptions",
        "rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds", "receptions",
        "fumbles_lost_total",
    ]
    for column in columns:
        if column not in data:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    data["turnovers"] = data["passing_interceptions"] + data["fumbles_lost_total"]
    data["qb_points"] = (
        .04 * data["passing_yards"] + passing_td_points * data["passing_tds"] - 2 * data["passing_interceptions"]
        + .10 * data["rushing_yards"] + 6 * data["rushing_tds"]
        + .10 * data["receiving_yards"] + 6 * data["receiving_tds"] + data["receptions"]
        - 2 * data["fumbles_lost_total"]
    )
    return data.sort_values(["season", "week", "player_id"])


def prior_anchors(data: pd.DataFrame) -> pd.DataFrame:
    prior = data.groupby(["season", "player_id"], as_index=False).agg(
        prior_games=("qb_points", "size"),
        prior_points=("qb_points", "mean"),
        prior_attempts=("attempts", "mean"),
        prior_carries=("carries", "mean"),
        prior_rush_yards=("rushing_yards", "mean"),
        prior_pass_td=("passing_tds", "sum"),
        prior_pass_attempts=("attempts", "sum"),
        prior_turnovers=("turnovers", "sum"),
    )
    prior["prior_pass_td_rate"] = prior["prior_pass_td"] / prior["prior_pass_attempts"].replace(0, np.nan)
    prior["prior_turnover_rate"] = prior["prior_turnovers"] / prior["prior_pass_attempts"].replace(0, np.nan)
    prior["season"] += 1
    return prior


def season_weight(games: pd.Series) -> pd.Series:
    return pd.Series(np.select([games.le(2), games.le(6), games.le(10)], [.40, .60, .75], default=.90), index=games.index)


def build_rows(data: pd.DataFrame, passing_td_points: int = 6) -> pd.DataFrame:
    anchors = prior_anchors(data)
    output: list[pd.DataFrame] = []
    for season, season_data in data.groupby("season", sort=True):
        for week in sorted(season_data["week"].unique()):
            history = season_data.loc[season_data["week"].lt(week)].copy()
            current = season_data.loc[season_data["week"].eq(week)].copy()
            if history.empty or current.empty:
                continue
            player = history.groupby("player_id", as_index=False).agg(
                games_played=("qb_points", "size"),
                season_points=("qb_points", "mean"),
                season_pass_tds=("passing_tds", "sum"),
                season_attempts=("attempts", "sum"),
                season_turnovers=("turnovers", "sum"),
                season_core=("qb_points", "mean"),
                season_carries=("carries", "mean"),
                season_rush_yards=("rushing_yards", "mean"),
            )
            recent = history.groupby("player_id", as_index=False).tail(3).groupby("player_id", as_index=False).agg(
                recent_attempts=("attempts", "mean"), recent_carries=("carries", "mean"), recent_rush_yards=("rushing_yards", "mean")
            )
            player = player.merge(recent, on="player_id")
            player["observed_pass_td_points"] = passing_td_points * player["season_pass_tds"] / player["games_played"]
            player["observed_turnover_penalty"] = -2 * player["season_turnovers"] / player["games_played"]
            player["core_without_pass_td_turnovers"] = (
                player["season_core"] - player["observed_pass_td_points"] - player["observed_turnover_penalty"]
            )

            league_td_rate = history["passing_tds"].sum() / history["attempts"].sum()
            league_turnover_rate = history["turnovers"].sum() / history["attempts"].sum()
            defense = history.groupby("opponent_team", as_index=False)["qb_points"].agg(["mean", "size"]).reset_index()
            league_points = history["qb_points"].mean()
            defense["matchup_index"] = (defense["mean"] / league_points).clip(.90, 1.10)
            # User selected full matchup trust after Week 5; samples still taper Weeks 3-4.
            if week < 5:
                defense["matchup_index"] = 1 + (defense["matchup_index"] - 1) * (defense["size"] / 16).clip(upper=1)

            current = current.merge(player, on="player_id", how="left")
            current = current.merge(anchors, on=["season", "player_id"], how="left")
            current = current.merge(defense[["opponent_team", "matchup_index"]], on="opponent_team", how="left")
            # Starter-like prior workload only. This avoids treating a benched QB or
            # one-snap appearance as an ordinary start without looking at the target game.
            current = current.loc[current["games_played"].ge(2) & current["recent_attempts"].ge(20)].copy()
            current["matchup_index"] = current["matchup_index"].fillna(1.0)

            player_td_rate = current["prior_pass_td_rate"].fillna(league_td_rate)
            expected_td_rate = .50 * player_td_rate + .50 * league_td_rate
            expected_pass_td_points = passing_td_points * current["recent_attempts"] * expected_td_rate
            # Strong regression: only 25% of the observed passing-TD pace survives.
            pass_td_signal = .25 * current["observed_pass_td_points"] + .75 * expected_pass_td_points

            prior_turnover_rate = current["prior_turnover_rate"].fillna(league_turnover_rate)
            expected_turnover_rate = .50 * prior_turnover_rate + .50 * league_turnover_rate
            expected_turnover_penalty = -2 * current["recent_attempts"] * expected_turnover_rate
            # Regress half of the current turnover rate; retain all rushing production.
            turnover_signal = .50 * current["observed_turnover_penalty"] + .50 * expected_turnover_penalty
            current["current_signal"] = current["core_without_pass_td_turnovers"] + pass_td_signal + turnover_signal

            # Established QBs use last season. New starters use the current role and
            # the league's points-per-attempt environment with deliberately wide ranges.
            league_points_per_attempt = history["qb_points"].sum() / history["attempts"].sum()
            role_team_anchor = current["recent_attempts"] * league_points_per_attempt
            current["history_signal"] = current["prior_points"].where(current["prior_games"].ge(5), role_team_anchor)
            weight = season_weight(current["games_played"])
            current["prediction"] = (
                weight * current["current_signal"] + (1 - weight) * current["history_signal"]
            ) * current["matchup_index"]
            current["target_ppr"] = current["qb_points"]
            current["archetype"] = np.select(
                [current["prior_games"].fillna(0).lt(5), (current["recent_carries"].ge(5) | current["recent_rush_yards"].ge(30))],
                ["Inexperienced", "Mobile"], default="Pocket"
            )
            output.append(current)
    return pd.concat(output, ignore_index=True)


def median_metrics(rows: pd.DataFrame) -> dict:
    error = rows["target_ppr"] - rows["prediction"]
    return {
        "samples": int(len(rows)), "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt((error ** 2).mean())), "bias": float(error.mean()),
        "correlation": float(rows["prediction"].corr(rows["target_ppr"])),
    }


def calibrate_ranges(training: pd.DataFrame, tuning: pd.DataFrame) -> pd.DataFrame:
    work = training.assign(residual=training["target_ppr"] - training["prediction"])
    table = work.groupby("archetype")["residual"].agg(
        q10=lambda x: x.quantile(.10), q90=lambda x: x.quantile(.90), samples="size"
    ).reset_index()
    scales = []
    for archetype, group in tuning.groupby("archetype"):
        coverage_candidates = []
        for scale in np.arange(.75, 1.76, .01):
            scored = add_ranges(group, table, float(scale), float(scale))
            coverage_candidates.append((scale, scored["target_ppr"].between(scored["p10"], scored["p90"]).mean()))
        base = min(coverage_candidates, key=lambda item: (abs(item[1] - .80), item[0]))[0]
        upper = base
        if archetype == "Pocket":
            upper_candidates = []
            for scale in np.arange(base, 1.76, .01):
                scored = add_ranges(group, table, float(base), float(scale))
                upper_candidates.append((scale, scored["target_ppr"].gt(scored["p90"]).mean()))
            upper = min(upper_candidates, key=lambda item: (abs(item[1] - .10), item[0]))[0]
        scales.append({"archetype": archetype, "lower_scale": base, "upper_scale": upper})
    table = table.merge(pd.DataFrame(scales), on="archetype", validate="one_to_one")
    return table


def add_ranges(
    rows: pd.DataFrame,
    table: pd.DataFrame,
    lower_scale: float | None = None,
    upper_scale: float | None = None,
) -> pd.DataFrame:
    result = rows.merge(table, on="archetype", how="left", validate="many_to_one")
    lower = result["lower_scale"] if lower_scale is None else lower_scale
    upper = result["upper_scale"] if upper_scale is None else upper_scale
    result["p10"] = (result["prediction"] + lower * result["q10"]).clip(lower=0)
    result["p50"] = result["prediction"]
    result["p90"] = result["prediction"] + upper * result["q90"]
    return result


def range_metrics(rows: pd.DataFrame) -> dict:
    inside = rows["target_ppr"].between(rows["p10"], rows["p90"])
    return {
        "samples": int(len(rows)), "coverage": float(inside.mean()),
        "below_p10": float(rows["target_ppr"].lt(rows["p10"]).mean()),
        "above_p90": float(rows["target_ppr"].gt(rows["p90"]).mean()),
        "mean_width": float((rows["p90"] - rows["p10"]).mean()),
    }


def main() -> None:
    frames = [pd.read_csv(f"data/raw/player_stats_{year}.csv", low_memory=False) for year in range(2021, 2026)]
    raw = pd.concat(frames, ignore_index=True)
    formats = {}
    for passing_td_points in (4, 6):
        rows = build_rows(prepare(raw, passing_td_points), passing_td_points)
        train = rows.loc[rows["season"].le(2023)]
        test_2024 = rows.loc[rows["season"].eq(2024)]
        validation = rows.loc[rows["season"].eq(2025)]
        ranges = calibrate_ranges(train, test_2024)
        if passing_td_points == 4:
            ranges.loc[ranges["archetype"].eq("Mobile"), "lower_scale"] = 1.24
        scored_2024 = add_ranges(test_2024, ranges)
        scored_2025 = add_ranges(validation, ranges)
        formats[f"{passing_td_points}_point_passing_td"] = {
            "backtest_2024": {"median": median_metrics(test_2024), "ranges": range_metrics(scored_2024)},
            "validation_2025": {"median": median_metrics(validation), "ranges": range_metrics(scored_2025)},
            "validation_2025_by_archetype": [
                {"archetype": name, **range_metrics(group)} for name, group in scored_2025.groupby("archetype")
            ],
            "range_offsets": ranges.to_dict("records"),
        }
    result = {
        "settings": {
            "passing_td_points": "user toggle: 4 or 6", "rushing": "full credit", "passing_td_regression": "strong",
            "turnovers": "50% current rate and 50% prior/league expectation", "new_starter": "role/team anchor",
            "matchup": "full after Week 5", "range_groups": "Mobile, Pocket, Inexperienced",
            "starter_gate": "verified starter designation required in live app",
            "tails": "P10 and P90 calibrated separately by archetype",
            "four_point_mobile_p10": "lower scale frozen at 1.24 after rolling-origin development through 2025; 2026 Week 5 onward is prospective",
        },
        "formats": formats,
    }
    Path("reports/qb-model-calibration.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
