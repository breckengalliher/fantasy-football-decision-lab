"""Freeze a four-point mobile-QB P10 scale using rolling-origin validation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from calibrate_qb_model import build_rows, prepare


def evaluate_scale(rows: pd.DataFrame, scale: float) -> tuple[list[dict], dict]:
    folds = []
    pooled_parts = []
    for validation_season in (2022, 2023, 2024, 2025):
        training = rows.loc[rows["season"].lt(validation_season) & rows["archetype"].eq("Mobile")]
        validation = rows.loc[rows["season"].eq(validation_season) & rows["archetype"].eq("Mobile")].copy()
        if len(training) < 30 or validation.empty:
            continue
        q10 = float((training["target_ppr"] - training["prediction"]).quantile(.10))
        validation["p10"] = (validation["prediction"] + scale * q10).clip(lower=0)
        validation["below"] = validation["target_ppr"].lt(validation["p10"])
        pooled_parts.append(validation[["below"]])
        folds.append({
            "validation_season": validation_season,
            "training_samples": int(len(training)),
            "validation_samples": int(len(validation)),
            "training_q10_residual": q10,
            "below_p10": float(validation["below"].mean()),
        })
    pooled = pd.concat(pooled_parts, ignore_index=True)
    summary = {
        "scale": scale,
        "folds": len(folds),
        "samples": int(len(pooled)),
        "pooled_below_p10": float(pooled["below"].mean()),
        "worst_fold_below_p10": max(fold["below_p10"] for fold in folds),
        "mean_fold_absolute_error_from_10pct": float(np.mean([abs(fold["below_p10"] - .10) for fold in folds])),
    }
    return folds, summary


def main() -> None:
    raw = pd.concat(
        [pd.read_csv(f"data/raw/player_stats_{year}.csv", low_memory=False) for year in range(2021, 2026)],
        ignore_index=True,
    )
    rows = build_rows(prepare(raw, passing_td_points=4), passing_td_points=4)
    candidates = []
    fold_map = {}
    for scale in np.arange(.80, 1.81, .01):
        folds, summary = evaluate_scale(rows, float(scale))
        candidates.append(summary)
        fold_map[round(float(scale), 2)] = folds
    grid = pd.DataFrame(candidates)
    # Honest downside takes precedence: pooled misses must be at or below 10%.
    eligible = grid.loc[grid["pooled_below_p10"].le(.10)].copy()
    eligible["score"] = (
        (eligible["pooled_below_p10"] - .10).abs()
        + .35 * eligible["mean_fold_absolute_error_from_10pct"]
        + .15 * (eligible["worst_fold_below_p10"] - .12).clip(lower=0)
    )
    selected = eligible.sort_values(["score", "scale"]).iloc[0].to_dict()
    selected_scale = round(float(selected["scale"]), 2)

    result = {
        "scope": "Four-point passing-TD mobile quarterbacks, P10 downside only",
        "method": "Rolling-origin validation: train only on earlier seasons and validate the next season",
        "development_seasons": [2021, 2022, 2023, 2024, 2025],
        "selected_lower_scale": selected_scale,
        "selection_summary": {key: value for key, value in selected.items() if key != "score"},
        "folds": fold_map[selected_scale],
        "prospective_test": {
            "season": 2026,
            "starts_with_week": 5,
            "status": "FROZEN_AWAITING_OUTCOMES",
            "success_rule": "At least 10 eligible mobile-QB starts before judging; target below-P10 rate 5%-15% and report exact binomial uncertainty.",
        },
    }
    Path("reports/mobile-qb-downside-cross-validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
