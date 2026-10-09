"""Reproducible, leakage-aware audit of the Sunday Decision Lab projection model.

This module is research infrastructure only.  It never writes the live board or
changes production formulas.  Historical rows are legitimate walk-forward
simulations built from weekly box scores available before the evaluated week;
they are not represented as archived published forecasts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_round_two import build_rows, prepare_weekly


POSITIONS = ("QB", "RB", "WR", "TE")


def load_history(raw_dir: Path, seasons: range = range(2021, 2026)) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = raw_dir / f"player_stats_{season}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Required historical input is missing: {path}")
        frames.append(pd.read_csv(path, low_memory=False))
    return prepare_weekly(pd.concat(frames, ignore_index=True))


def historical_data_audit(data: pd.DataFrame) -> dict:
    key = ["season", "week", "player_id"]
    required = ["player_id", "season", "week", "position", "opponent_team", "fantasy_points_ppr"]
    feature_availability = {}
    for label, fields in {
        "box_score_opportunity": ["attempts", "carries", "targets"],
        "receiving_efficiency": ["receiving_yards", "receiving_air_yards", "target_share"],
        "routes_and_first_read": ["routes", "route_participation", "first_read_share"],
        "snaps": ["offense_snaps", "snap_pct"],
        "historical_injury_timestamp": ["injury_status", "injury_updated_at"],
        "historical_market_timestamp": ["market_line", "market_timestamp"],
    }.items():
        present = [field for field in fields if field in data.columns]
        feature_availability[label] = {
            "required_fields": fields,
            "present_fields": present,
            "complete": len(present) == len(fields),
        }
    return {
        "rows": int(len(data)),
        "seasons": sorted(map(int, data["season"].unique())),
        "regular_season_rows": int(data["season_type"].eq("REG").sum()) if "season_type" in data else None,
        "positions": data["position"].value_counts().to_dict(),
        "duplicate_player_weeks": int(data.duplicated(key).sum()),
        "missing_required": {field: int(data[field].isna().sum()) if field in data else int(len(data)) for field in required},
        "feature_availability": feature_availability,
        "point_in_time_classification": "walk-forward box-score simulation; not an archive of published forecasts",
    }


def add_simple_benchmarks(data: pd.DataFrame, incumbent: pd.DataFrame) -> pd.DataFrame:
    ordered = data.sort_values(["season", "player_id", "week"]).copy()
    group = ordered.groupby(["season", "player_id"], sort=False)
    prior = group["fantasy_points_ppr"].shift(1)
    ordered["season_average"] = prior.groupby([ordered["season"], ordered["player_id"]]).expanding().mean().reset_index(level=[0, 1], drop=True)
    ordered["rolling_3"] = prior.groupby([ordered["season"], ordered["player_id"]]).rolling(3, min_periods=1).mean().reset_index(level=[0, 1], drop=True)
    ordered["rolling_5"] = prior.groupby([ordered["season"], ordered["player_id"]]).rolling(5, min_periods=1).mean().reset_index(level=[0, 1], drop=True)
    ordered["ewm"] = prior.groupby([ordered["season"], ordered["player_id"]]).transform(
        lambda values: values.ewm(alpha=.35, adjust=False, min_periods=1).mean()
    )
    keys = ["season", "week", "player_id", "position"]
    simple = ordered[keys + ["season_average", "rolling_3", "rolling_5", "ewm"]]
    result = incumbent.merge(simple, on=keys, how="left", validate="one_to_one")
    result["incumbent"] = result["prediction"]
    result["opportunity_only"] = result["recent_opportunities"] * result["current_ppr_rate"]
    return result


def fit_regularized_model(rows: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    numeric = [
        "games_played", "season_ppr", "season_td", "recent_opportunities",
        "recent_opportunity_share", "prior_ppr", "prior_opportunities",
        "prior_opportunity_share", "current_ppr_rate", "current_td_rate", "matchup_index",
    ]
    train = rows.loc[rows["season"].le(2023)].copy()
    validation = rows.loc[rows["season"].eq(2024)].copy()
    test = rows.loc[rows["season"].eq(2025)].copy()

    def design(frame: pd.DataFrame, medians: pd.Series, means: pd.Series, scales: pd.Series) -> np.ndarray:
        values = frame[numeric].apply(pd.to_numeric, errors="coerce").fillna(medians)
        values = (values - means) / scales
        positions = pd.get_dummies(frame["position"], dtype=float).reindex(columns=POSITIONS, fill_value=0.0)
        return np.column_stack([np.ones(len(frame)), positions.to_numpy(), values.to_numpy()])

    def fit_predict(fit: pd.DataFrame, score: pd.DataFrame, alpha: float) -> np.ndarray:
        medians = fit[numeric].apply(pd.to_numeric, errors="coerce").median()
        clean = fit[numeric].apply(pd.to_numeric, errors="coerce").fillna(medians)
        means = clean.mean()
        scales = clean.std().replace(0, 1).fillna(1)
        matrix = design(fit, medians, means, scales)
        target = fit["target_ppr"].to_numpy(dtype=float)
        penalty = np.eye(matrix.shape[1]) * alpha
        penalty[0, 0] = 0.0  # Do not penalize the intercept.
        coefficients = np.linalg.solve(matrix.T @ matrix + penalty, matrix.T @ target)
        return design(score, medians, means, scales) @ coefficients

    validation_results = []
    for alpha in (1.0, 10.0, 100.0, 1000.0):
        prediction = fit_predict(train, validation, alpha)
        validation_results.append({"alpha": alpha, "mae": float(np.mean(np.abs(validation["target_ppr"] - prediction)))})
    selected = min(validation_results, key=lambda item: item["mae"])["alpha"]
    final_train = rows.loc[rows["season"].le(2024)].copy()
    test["regularized_opportunity_efficiency"] = fit_predict(final_train, test, selected)
    return test, {"selected_alpha": selected, "validation": validation_results, "training_seasons": [2021, 2022, 2023, 2024], "test_season": 2025}


def metric_summary(rows: pd.DataFrame, prediction: str) -> dict:
    clean = rows[["target_ppr", prediction]].dropna()
    error = clean["target_ppr"] - clean[prediction]
    return {
        "samples": int(len(clean)),
        "mae": float(error.abs().mean()),
        "median_absolute_error": float(error.abs().median()),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "bias_actual_minus_projection": float(error.mean()),
        "extreme_miss_rate_over_15": float(error.abs().gt(15).mean()),
    }


def pairwise_breakdown(rows: pd.DataFrame, prediction: str) -> dict:
    buckets = {"0-2": [0, 0], "2-5": [0, 0], "5-10": [0, 0], "10+": [0, 0]}
    by_combo: dict[str, list[int]] = {}
    week_scores = []
    for (season, week), week_rows in rows.dropna(subset=[prediction, "target_ppr"]).groupby(["season", "week"]):
        values = week_rows.reset_index(drop=True)
        left, right = np.triu_indices(len(values), 1)
        projected = values[prediction].to_numpy(dtype=float)
        actual = values["target_ppr"].to_numpy(dtype=float)
        projected_gap = projected[left] - projected[right]
        actual_gap = actual[left] - actual[right]
        usable = (projected_gap != 0) & (actual_gap != 0)
        projected_gap = projected_gap[usable]
        actual_gap = actual_gap[usable]
        left = left[usable]; right = right[usable]
        hit = (projected_gap * actual_gap > 0).astype(int)
        gap = np.abs(projected_gap)
        labels = np.select([gap < 2, gap < 5, gap < 10], ["0-2", "2-5", "5-10"], default="10+")
        for label in buckets:
            mask = labels == label
            buckets[label][0] += int(hit[mask].sum()); buckets[label][1] += int(mask.sum())
        positions = values["position"].astype(str).to_numpy()
        combos = np.array(["-".join(sorted(pair)) for pair in zip(positions[left], positions[right])])
        for combo in np.unique(combos):
            mask = combos == combo
            by_combo.setdefault(combo, [0, 0])
            by_combo[combo][0] += int(hit[mask].sum()); by_combo[combo][1] += int(mask.sum())
        correct = int(hit.sum()); total = int(len(hit))
        if total:
            week_scores.append({"season": int(season), "week": int(week), "accuracy": correct / total, "pairs": total})
    summarize = lambda item: {"accuracy": item[0] / item[1] if item[1] else None, "pairs": item[1]}
    weighted_correct = sum(item[0] for item in buckets.values())
    weighted_total = sum(item[1] for item in buckets.values())
    weekly = pd.DataFrame(week_scores)
    rng = np.random.default_rng(2026)
    boot = []
    if not weekly.empty:
        values = weekly["accuracy"].to_numpy()
        for _ in range(2000):
            boot.append(float(rng.choice(values, size=len(values), replace=True).mean()))
    return {
        "accuracy": weighted_correct / weighted_total if weighted_total else None,
        "pairs": weighted_total,
        "gap_buckets": {key: summarize(value) for key, value in buckets.items()},
        "position_combinations": {key: summarize(value) for key, value in sorted(by_combo.items())},
        "week_clustered_95_interval": list(map(float, np.quantile(boot, [.025, .975]))) if boot else [None, None],
    }


def segmented_metrics(rows: pd.DataFrame, prediction: str) -> dict:
    output = {"position": {}}
    for position, group in rows.groupby("position"):
        output["position"][position] = metric_summary(group, prediction)
    output["season_phase"] = {
        "weeks_3_to_8": metric_summary(rows.loc[rows["week"].le(8)], prediction),
        "weeks_9_plus": metric_summary(rows.loc[rows["week"].ge(9)], prediction),
    }
    workload = pd.qcut(rows["recent_opportunities"], q=3, labels=["low", "medium", "high"], duplicates="drop")
    output["workload"] = {str(level): metric_summary(rows.loc[workload.eq(level)], prediction) for level in workload.dropna().unique()}
    output["history"] = {
        "sparse_2_to_4_games": metric_summary(rows.loc[rows["games_played"].le(4)], prediction),
        "established_5_plus_games": metric_summary(rows.loc[rows["games_played"].ge(5)], prediction),
    }
    return output


def clustered_metric_difference(
    rows: pd.DataFrame,
    challenger: str,
    incumbent: str,
    samples: int = 4000,
) -> dict:
    """Bootstrap season-week clusters; negative MAE difference favors challenger."""
    comparison = rows.dropna(subset=[challenger, incumbent, "target_ppr"]).copy()
    comparison["challenger_error"] = (comparison["target_ppr"] - comparison[challenger]).abs()
    comparison["incumbent_error"] = (comparison["target_ppr"] - comparison[incumbent]).abs()
    clusters = [group for _, group in comparison.groupby(["season", "week"])]
    point = float((comparison["challenger_error"] - comparison["incumbent_error"]).mean())
    rng = np.random.default_rng(2026)
    differences = []
    for _ in range(samples):
        chosen = rng.integers(0, len(clusters), len(clusters))
        sample = pd.concat([clusters[index] for index in chosen], ignore_index=True)
        differences.append(float((sample["challenger_error"] - sample["incumbent_error"]).mean()))
    low, high = np.quantile(differences, [.025, .975])
    return {"mae_difference": point, "week_clustered_95_interval": [float(low), float(high)], "clusters": len(clusters)}


def interval_audit(rows: pd.DataFrame, report_path: Path) -> dict:
    calibration = json.loads(report_path.read_text(encoding="utf-8"))
    validation = calibration["validation_2025"]
    return {
        "source": str(report_path),
        "interval": "production empirical P10-P90 residual range",
        "samples": validation["samples"],
        "coverage": validation["coverage"],
        "mean_width": validation["mean_width"],
        "target_coverage": .80,
        "note": "P20-P80 remains experimental; the current production interval is unchanged.",
    }


def run_audit(raw_dir: Path, output_dir: Path) -> dict:
    data = load_history(raw_dir)
    incumbent_rows = build_rows(data, round_three=True)
    rows = add_simple_benchmarks(data, incumbent_rows)
    test, regularization = fit_regularized_model(rows)
    shared_columns = ["season", "week", "player_id"]
    test = test.merge(
        rows[shared_columns + ["incumbent", "season_average", "rolling_3", "rolling_5", "ewm", "opportunity_only"]],
        on=shared_columns, how="left", suffixes=("", "_benchmark"), validate="one_to_one",
    )
    benchmark_names = ["incumbent", "season_average", "rolling_3", "rolling_5", "ewm", "opportunity_only", "regularized_opportunity_efficiency"]
    benchmarks = {}
    for name in benchmark_names:
        column = name if name in test else f"{name}_benchmark"
        benchmarks[name] = {
            "point_accuracy": metric_summary(test, column),
            "start_sit": pairwise_breakdown(test, column),
        }
    incumbent_column = "incumbent" if "incumbent" in test else "incumbent_benchmark"
    regularized_comparison = clustered_metric_difference(
        test, "regularized_opportunity_efficiency", incumbent_column
    )
    result = {
        "study_classification": "legitimate walk-forward simulation; not archived published forecasts",
        "evaluation": {"train": "2021-2023", "model_selection": "2024", "final_test": "2025", "scoring": "full PPR with 4-point passing TDs"},
        "data_quality": historical_data_audit(data),
        "benchmarks_2025": benchmarks,
        "incumbent_segments_2025": segmented_metrics(test, incumbent_column),
        "regularized_segments_2025": segmented_metrics(test, "regularized_opportunity_efficiency"),
        "regularized_model": regularization,
        "regularized_vs_incumbent": regularized_comparison,
        "production_interval_audit": interval_audit(rows, ROOT / "reports" / "projection-range-calibration.json"),
        "known_gaps": [
            "No immutable archive of exact user-visible pregame projections exists before this audit.",
            "Historical injury, depth-chart, route, snap, first-read, weather, and market states are not fully timestamped in the local archive.",
            "The 2021-2025 historical evaluation validates full PPR with four-point passing TDs; six-point QB results require a separately specified walk-forward reconstruction.",
            "Pairwise comparisons are correlated; week-clustered uncertainty is reported and raw pair counts are not treated as independent samples.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model-validation-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary_rows = []
    for model, values in benchmarks.items():
        summary_rows.append({"model": model, **values["point_accuracy"], "pairwise_accuracy": values["start_sit"]["accuracy"]})
    pd.DataFrame(summary_rows).to_csv(output_dir / "benchmark-summary-2025.csv", index=False)
    incumbent_pairs = benchmarks["incumbent"]["start_sit"]["gap_buckets"]
    pd.DataFrame([
        {"projected_gap": gap, "ordering_accuracy": values["accuracy"], "pairs": values["pairs"]}
        for gap, values in incumbent_pairs.items()
    ]).to_csv(output_dir / "ordering-by-gap-2025.csv", index=False)
    incumbent_position = result["incumbent_segments_2025"]["position"]
    challenger_position = result["regularized_segments_2025"]["position"]
    pd.DataFrame([
        {
            "position": position,
            "incumbent_mae": incumbent_position[position]["mae"],
            "challenger_mae": challenger_position[position]["mae"],
            "samples": incumbent_position[position]["samples"],
        }
        for position in POSITIONS
    ]).to_csv(output_dir / "position-mae-2025.csv", index=False)
    test.loc[:, ["season", "week", "player_id", "player_display_name", "position", "target_ppr", *[c for c in benchmark_names if c in test]]].to_parquet(
        output_dir / "benchmark-predictions-2025.parquet", index=False
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "model-validation-audit")
    args = parser.parse_args()
    result = run_audit(args.raw_dir, args.output_dir)
    print(json.dumps({"output": str(args.output_dir), "benchmarks": result["benchmarks_2025"]}, indent=2))


if __name__ == "__main__":
    main()
