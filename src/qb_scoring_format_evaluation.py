"""Separate chronological evaluation of the approved QB formula in 4/6-point formats."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_round_two import prepare_weekly


def add_qb_scoring(data: pd.DataFrame, passing_td_points: int) -> pd.DataFrame:
    result = data.copy()
    interception_column = "passing_interceptions" if "passing_interceptions" in result else "interceptions"
    if interception_column not in result:
        result[interception_column] = 0.0
    if "fumbles_lost_total" not in result:
        result["fumbles_lost_total"] = 0.0
    for column in (interception_column, "fumbles_lost_total", "passing_tds"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    result["qb_points"] = result["fantasy_points_ppr"] + (passing_td_points - 4) * result["passing_tds"]
    result["turnovers"] = result[interception_column] + result["fumbles_lost_total"]
    return result


def build_qb_rows(data: pd.DataFrame, passing_td_points: int) -> pd.DataFrame:
    scored = add_qb_scoring(data.loc[data["position"].eq("QB")].copy(), passing_td_points)
    anchors = scored.groupby(["season", "player_id"], as_index=False).agg(
        prior_games=("qb_points", "size"), prior_points=("qb_points", "mean"),
        prior_tds=("passing_tds", "sum"), prior_attempts=("attempts", "sum"),
        prior_turnovers=("turnovers", "sum"),
    )
    anchors["prior_td_rate"] = anchors["prior_tds"] / anchors["prior_attempts"].replace(0, np.nan)
    anchors["prior_turnover_rate"] = anchors["prior_turnovers"] / anchors["prior_attempts"].replace(0, np.nan)
    anchors["season"] += 1
    output = []
    for season, season_data in scored.groupby("season", sort=True):
        for week in sorted(season_data["week"].unique()):
            history = season_data.loc[season_data["week"].lt(week)].copy()
            current = season_data.loc[season_data["week"].eq(week)].copy()
            if history.empty:
                continue
            aggregate = history.groupby("player_id", as_index=False).agg(
                games_played=("qb_points", "size"), season_points=("qb_points", "mean"),
                pass_tds=("passing_tds", "sum"), attempts=("attempts", "sum"),
                observed_turnovers=("turnovers", "sum"),
            )
            recent = history.sort_values(["player_id", "week"]).groupby("player_id", as_index=False).tail(3)
            recent = recent.groupby("player_id", as_index=False).agg(
                recent_attempts=("attempts", "mean"), recent_carries=("carries", "mean"),
                recent_rush_yards=("rushing_yards", "mean"), recent_points=("qb_points", "mean"),
            )
            rows = current.merge(aggregate, on="player_id", how="left").merge(recent, on="player_id", how="left")
            rows = rows.merge(anchors, on=["season", "player_id"], how="left")
            rows = rows.loc[rows["games_played"].ge(2) & rows["recent_attempts"].ge(12)].copy()
            if rows.empty:
                continue
            observed_td = passing_td_points * rows["pass_tds"] / rows["games_played"]
            observed_turnover = -2 * rows["observed_turnovers"] / rows["games_played"]
            core = rows["season_points"] - observed_td - observed_turnover
            league_td_rate = history["passing_tds"].sum() / history["attempts"].sum()
            league_turnover_rate = history["turnovers"].sum() / history["attempts"].sum()
            td_rate = .5 * rows["prior_td_rate"].fillna(league_td_rate) + .5 * league_td_rate
            turnover_rate = .5 * rows["prior_turnover_rate"].fillna(league_turnover_rate) + .5 * league_turnover_rate
            td_signal = .25 * observed_td + .75 * passing_td_points * rows["recent_attempts"] * td_rate
            turnover_signal = .5 * observed_turnover + .5 * -2 * rows["recent_attempts"] * turnover_rate
            current_signal = core + td_signal + turnover_signal
            points_per_attempt = history["qb_points"].sum() / history["attempts"].sum()
            role_anchor = rows["recent_attempts"] * points_per_attempt
            history_signal = rows["prior_points"].where(rows["prior_games"].ge(5), role_anchor)
            weight = np.select(
                [rows["games_played"].le(2), rows["games_played"].le(6), rows["games_played"].le(10)],
                [.40, .60, .75], default=.90,
            )
            rows["projection_base"] = weight * current_signal + (1 - weight) * history_signal
            defense = history.groupby("opponent_team", as_index=False)["qb_points"].agg(["mean", "size"]).reset_index()
            defense["factor"] = (defense["mean"] / history["qb_points"].mean()).clip(.90, 1.10)
            if week < 5:
                defense["factor"] = 1 + (defense["factor"] - 1) * (defense["size"] / 16).clip(upper=1)
            rows = rows.merge(defense[["opponent_team", "factor"]], on="opponent_team", how="left")
            rows["projection"] = rows["projection_base"] * rows["factor"].fillna(1.0)
            rows["target_ppr"] = rows["qb_points"]
            rows["season_average"] = rows["season_points"]
            rows["rolling_three"] = rows["recent_points"]
            output.append(rows)
    return pd.concat(output, ignore_index=True)


def metrics(rows: pd.DataFrame, prediction: str) -> dict:
    error = rows["target_ppr"] - rows[prediction]
    correct = total = 0
    for _, group in rows.groupby(["season", "week"]):
        projected = group[prediction].to_numpy()
        actual = group["target_ppr"].to_numpy()
        left, right = np.triu_indices(len(group), 1)
        usable = (projected[left] != projected[right]) & (actual[left] != actual[right])
        correct += int((((projected[left] - projected[right]) * (actual[left] - actual[right]) > 0) & usable).sum())
        total += int(usable.sum())
    return {
        "samples": int(len(rows)), "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "bias_actual_minus_projection": float(error.mean()),
        "pairwise_ordering_accuracy": float(correct / total) if total else None,
        "eligible_pairs": total,
    }


def main() -> None:
    raw = pd.concat([
        pd.read_csv(ROOT / "data" / "raw" / f"player_stats_{season}.csv", low_memory=False)
        for season in range(2021, 2026)
    ], ignore_index=True)
    prepared = prepare_weekly(raw)
    results = {"classification": "walk-forward QB simulation; not archived published forecasts", "formats": {}}
    for points in (4, 6):
        rows = build_qb_rows(prepared, points)
        test = rows.loc[rows["season"].eq(2025)].copy()
        results["formats"][str(points)] = {
            "approved_qb_formula": metrics(test, "projection"),
            "season_average": metrics(test, "season_average"),
            "rolling_three": metrics(test, "rolling_three"),
        }
    output = ROOT / "reports" / "model-validation-audit" / "qb-scoring-format-evaluation.json"
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
