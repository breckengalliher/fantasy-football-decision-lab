"""Calibrate 10th/90th percentile bands around the approved round-three median."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from model_round_two import build_rows, prepare_weekly


def sample_bucket(games: pd.Series) -> pd.Categorical:
    return pd.cut(games, bins=[0, 4, 8, np.inf], labels=["2-4", "5-8", "9+"])


def interval_table(training: pd.DataFrame) -> pd.DataFrame:
    work = training.copy()
    work["sample_bucket"] = sample_bucket(work["games_played"])
    work["residual"] = work["target_ppr"] - work["prediction"]
    table = work.groupby(["position", "sample_bucket"], observed=True)["residual"].agg(
        q10=lambda values: values.quantile(.10),
        q90=lambda values: values.quantile(.90),
        samples="size",
    ).reset_index()
    return table


def attach_intervals(rows: pd.DataFrame, table: pd.DataFrame, scale: float = 1.0) -> pd.DataFrame:
    result = rows.copy()
    result["sample_bucket"] = sample_bucket(result["games_played"])
    result = result.merge(table, on=["position", "sample_bucket"], how="left", validate="many_to_one")
    result["p10"] = (result["prediction"] + scale * result["q10"]).clip(lower=0)
    result["p50"] = result["prediction"]
    result["p90"] = (result["prediction"] + scale * result["q90"]).clip(lower=0)
    return result


def coverage(rows: pd.DataFrame) -> dict:
    inside = rows["target_ppr"].between(rows["p10"], rows["p90"])
    below = rows["target_ppr"].lt(rows["p10"])
    above = rows["target_ppr"].gt(rows["p90"])
    return {
        "samples": int(len(rows)),
        "coverage": float(inside.mean()),
        "below_p10": float(below.mean()),
        "above_p90": float(above.mean()),
        "mean_width": float((rows["p90"] - rows["p10"]).mean()),
    }


def grouped_coverage(rows: pd.DataFrame) -> list[dict]:
    output = []
    for (position, bucket), group in rows.groupby(["position", "sample_bucket"], observed=True):
        output.append({"position": position, "sample_bucket": str(bucket), **coverage(group)})
    return output


def main() -> None:
    frames = [pd.read_csv(f"data/raw/player_stats_{season}.csv", low_memory=False) for season in range(2021, 2026)]
    rows = build_rows(prepare_weekly(pd.concat(frames, ignore_index=True)), round_three=True)
    training = rows.loc[rows["season"].le(2023)].copy()
    check_2024 = rows.loc[rows["season"].eq(2024)].copy()
    untouched_2025 = rows.loc[rows["season"].eq(2025)].copy()
    table = interval_table(training)

    candidates = []
    for scale in np.arange(.80, 1.51, .01):
        scored = attach_intervals(check_2024, table, float(scale))
        stats = coverage(scored)
        candidates.append({"scale": float(scale), **stats})
    tuning = pd.DataFrame(candidates)
    tuning["distance"] = (tuning["coverage"] - .80).abs()
    selected_scale = float(tuning.sort_values(["distance", "mean_width"]).iloc[0]["scale"])

    scored_2024 = attach_intervals(check_2024, table, selected_scale)
    scored_2025 = attach_intervals(untouched_2025, table, selected_scale)
    scaled_table = table.copy()
    scaled_table["p10_offset"] = scaled_table["q10"] * selected_scale
    scaled_table["p90_offset"] = scaled_table["q90"] * selected_scale

    wr_early = scaled_table.loc[
        scaled_table["position"].eq("WR") & scaled_table["sample_bucket"].astype(str).eq("2-4")
    ].iloc[0]
    live_medians = {"Jaxon Smith-Njigba": 21.588874, "CeeDee Lamb": 21.347722, "Nico Collins": 16.479700}
    live = [
        {
            "player": player,
            "p10": max(0.0, median + float(wr_early["p10_offset"])),
            "p50": median,
            "p90": median + float(wr_early["p90_offset"]),
        }
        for player, median in live_medians.items()
    ]

    result = {
        "definition": "P10/P50/P90 conditional outcome range; approximately 80% of games should land from P10 through P90.",
        "training_seasons": [2021, 2022, 2023],
        "scale_tuning_season": 2024,
        "untouched_validation_season": 2025,
        "selected_scale": selected_scale,
        "check_2024": coverage(scored_2024),
        "validation_2025": coverage(scored_2025),
        "validation_2025_by_position_and_sample": grouped_coverage(scored_2025),
        "offsets": scaled_table[["position", "sample_bucket", "p10_offset", "p90_offset", "samples"]].to_dict("records"),
        "live_week_5": live,
    }
    Path("reports/projection-range-calibration.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
