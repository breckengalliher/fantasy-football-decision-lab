"""Leakage-safe historical validation for the live Start/Sit projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

NFLVERSE_WEEKLY = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/stats_player_week_{season}.parquet"
POSITIONS = ("QB", "RB", "WR", "TE")
OPPORTUNITY_FLOORS = {"QB": 12.0, "RB": 5.0, "WR": 3.0, "TE": 2.0}


def build_backtest_rows(weekly: pd.DataFrame, min_prior_games: int = 3) -> pd.DataFrame:
    """Build one prediction row per player-week using strictly earlier games."""
    data = weekly.copy()
    data = data.loc[data["position"].isin(POSITIONS)].copy()
    data["fantasy_points_ppr"] = pd.to_numeric(data["fantasy_points_ppr"], errors="coerce")
    data = data.loc[data["fantasy_points_ppr"].notna()].sort_values(["season", "week", "player_id"])
    for column in ("attempts", "carries", "targets"):
        if column not in data:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    data["opportunities"] = np.where(
        data["position"].eq("QB"), data["attempts"] + data["carries"], data["carries"] + data["targets"]
    )

    output: list[pd.DataFrame] = []
    for season, season_data in data.groupby("season", sort=True):
        for week in sorted(season_data["week"].unique()):
            history = season_data.loc[season_data["week"].lt(week)].copy()
            current = season_data.loc[season_data["week"].eq(week)].copy()
            if history.empty or current.empty:
                continue
            player_history = history.sort_values(["player_id", "week"])
            features = player_history.groupby("player_id").agg(
                season_ppr=("fantasy_points_ppr", "mean"),
                games_played=("fantasy_points_ppr", "size"),
            )
            features["recent_ppr"] = player_history.groupby("player_id")["fantasy_points_ppr"].apply(
                lambda values: values.tail(4).mean()
            )
            features["recent_opportunities"] = player_history.groupby("player_id")["opportunities"].apply(
                lambda values: values.tail(3).mean()
            )

            defense = history.groupby(["opponent_team", "position"])["fantasy_points_ppr"].agg(
                points_allowed="mean", matchup_samples="size"
            ).reset_index()
            league = history.groupby("position")["fantasy_points_ppr"].mean().rename("league_ppr")
            defense = defense.merge(league, on="position", how="left")
            defense["matchup_index"] = (defense["points_allowed"] / defense["league_ppr"]).clip(.85, 1.15)

            current = current.merge(features, on="player_id", how="left")
            current = current.merge(defense, on=["opponent_team", "position"], how="left")
            current["matchup_index"] = current["matchup_index"].fillna(1.0)
            floor = current["position"].map(OPPORTUNITY_FLOORS)
            current = current.loc[
                current["games_played"].ge(min_prior_games)
                & current["recent_opportunities"].ge(floor)
            ].copy()
            current["target_ppr"] = current["fantasy_points_ppr"]
            output.append(current)
    return pd.concat(output, ignore_index=True) if output else pd.DataFrame()


def score_configuration(rows: pd.DataFrame, recent_weight: float, matchup_strength: float) -> dict:
    prediction = (
        recent_weight * rows["recent_ppr"] + (1 - recent_weight) * rows["season_ppr"]
    ) * (1 + matchup_strength * (rows["matchup_index"] - 1))
    error = rows["target_ppr"] - prediction
    correlation = (
        float(prediction.corr(rows["target_ppr"]))
        if prediction.nunique() > 1 and rows["target_ppr"].nunique() > 1
        else float("nan")
    )
    return {
        "recent_weight": recent_weight,
        "matchup_strength": matchup_strength,
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt((error ** 2).mean())),
        "bias": float(error.mean()),
        "correlation": correlation,
    }


def calibrate(rows: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    grid = pd.DataFrame([
        score_configuration(rows, recent, matchup)
        for recent in np.arange(0, 1.01, .05)
        for matchup in (0.0, .10, .25, .40)
    ]).sort_values(["mae", "rmse"])
    best = grid.iloc[0].to_dict()
    prediction = (
        best["recent_weight"] * rows["recent_ppr"]
        + (1 - best["recent_weight"]) * rows["season_ppr"]
    ) * (1 + best["matchup_strength"] * (rows["matchup_index"] - 1))
    residuals = rows.assign(residual=rows["target_ppr"] - prediction)
    intervals = residuals.groupby("position")["residual"].quantile([.20, .50, .80]).unstack()
    intervals.columns = ["floor_offset", "median_offset", "ceiling_offset"]
    intervals["samples"] = residuals.groupby("position").size()
    intervals = intervals.reset_index()
    return grid, best, intervals


def add_prediction(rows: pd.DataFrame, recent_weight: float, matchup_strength: float) -> pd.DataFrame:
    result = rows.copy()
    result["prediction"] = (
        recent_weight * result["recent_ppr"] + (1 - recent_weight) * result["season_ppr"]
    ) * (1 + matchup_strength * (result["matchup_index"] - 1))
    result["absolute_error"] = (result["target_ppr"] - result["prediction"]).abs()
    return result


def pairwise_ordering_accuracy(rows: pd.DataFrame) -> float:
    """Share of same-week, same-position player pairs ordered correctly."""
    correct = total = 0
    for _, group in rows.groupby(["season", "week", "position"]):
        prediction = group["prediction"].to_numpy()
        actual = group["target_ppr"].to_numpy()
        i, j = np.triu_indices(len(group), 1)
        usable = (prediction[i] != prediction[j]) & (actual[i] != actual[j])
        correct += int(((prediction[i] - prediction[j]) * (actual[i] - actual[j]) > 0)[usable].sum())
        total += int(usable.sum())
    return correct / total if total else float("nan")


def clustered_mae_difference_ci(
    rows: pd.DataFrame,
    challenger: tuple[float, float],
    incumbent: tuple[float, float],
    samples: int = 2000,
    seed: int = 2026,
) -> tuple[float, float, float]:
    """Bootstrap game-week clusters; negative differences favor the challenger."""
    new = add_prediction(rows, *challenger)
    old = add_prediction(rows, *incumbent)
    comparison = new[["season", "week", "absolute_error"]].rename(columns={"absolute_error": "new"})
    comparison["old"] = old["absolute_error"].to_numpy()
    clusters = [group for _, group in comparison.groupby(["season", "week"])]
    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(samples):
        picked = rng.integers(0, len(clusters), len(clusters))
        sample = pd.concat([clusters[index] for index in picked], ignore_index=True)
        differences.append(float((sample["new"] - sample["old"]).mean()))
    point = float((comparison["new"] - comparison["old"]).mean())
    low, high = np.quantile(differences, [.025, .975])
    return point, float(low), float(high)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, default=[2021, 2022, 2023, 2024])
    parser.add_argument("--output", type=Path, default=Path("reports/start_sit_backtest"))
    args = parser.parse_args()
    frames = []
    for season in args.seasons:
        local = Path(f"data/raw/player_stats_{season}.parquet")
        frames.append(pd.read_parquet(local if local.exists() else NFLVERSE_WEEKLY.format(season=season)))
    weekly = pd.concat(frames, ignore_index=True)
    rows = build_backtest_rows(weekly)
    grid, best, intervals = calibrate(rows)
    holdout = rows.loc[rows["season"].eq(max(args.seasons))].copy()
    training = rows.loc[rows["season"].lt(max(args.seasons))].copy()
    _, training_best, training_intervals = calibrate(training)
    calibrated_holdout = add_prediction(holdout, training_best["recent_weight"], training_best["matchup_strength"])
    previous_holdout = add_prediction(holdout, .65, .25)
    ci = clustered_mae_difference_ci(
        holdout,
        (training_best["recent_weight"], training_best["matchup_strength"]),
        (.65, .25),
    )
    offsets = training_intervals.set_index("position")
    lower = calibrated_holdout["prediction"] + calibrated_holdout["position"].map(offsets["floor_offset"])
    upper = calibrated_holdout["prediction"] + calibrated_holdout["position"].map(offsets["ceiling_offset"])
    coverage = float(calibrated_holdout["target_ppr"].between(lower, upper).mean())
    args.output.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(args.output / "prediction_rows.parquet", index=False)
    grid.to_csv(args.output / "grid_results.csv", index=False)
    intervals.to_csv(args.output / "interval_calibration.csv", index=False)
    summary = {
        "seasons": args.seasons,
        "predictions": len(rows),
        "all_season_best": best,
        "training_best": training_best,
        "holdout_season": max(args.seasons),
        "holdout_predictions": len(holdout),
        "holdout_calibrated": score_configuration(holdout, training_best["recent_weight"], training_best["matchup_strength"]),
        "holdout_previous": score_configuration(holdout, .65, .25),
        "mae_difference_95_ci": {"point": ci[0], "low": ci[1], "high": ci[2]},
        "pairwise_accuracy_calibrated": pairwise_ordering_accuracy(calibrated_holdout),
        "pairwise_accuracy_previous": pairwise_ordering_accuracy(previous_holdout),
        "interval_20_80_holdout_coverage": coverage,
        "intervals": training_intervals.to_dict("records"),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
