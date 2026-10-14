"""Record and score prospective 2026 four-point mobile-QB P10 forecasts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from calibrate_qb_model import prepare, prior_anchors, season_weight


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "reports" / "mobile-qb-2026-prospective.csv"
LOWER_SCALE = 1.24


def score_existing(ledger: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    actual = weekly[["player_id", "week", "qb_points"]].rename(columns={"qb_points": "actual_points"})
    result = ledger.drop(columns=["actual_points", "below_p10"], errors="ignore").merge(
        actual, left_on=["player_id", "target_week"], right_on=["player_id", "week"], how="left"
    ).drop(columns="week", errors="ignore")
    result["below_p10"] = np.where(result["actual_points"].notna(), result["actual_points"] < result["p10"], pd.NA)
    return result


def current_forecasts(weekly: pd.DataFrame, board: pd.DataFrame, prior: pd.DataFrame, target_week: int) -> pd.DataFrame:
    history = weekly.loc[weekly["week"].lt(target_week)].copy()
    features = history.groupby("player_id", as_index=False).agg(
        games_played=("qb_points", "size"), season_points=("qb_points", "mean"),
        season_pass_tds=("passing_tds", "sum"), season_attempts=("attempts", "sum"),
        season_turnovers=("turnovers", "sum"), season_carries=("carries", "mean"),
        season_rush_yards=("rushing_yards", "mean"),
    )
    recent = history.groupby("player_id", as_index=False).tail(3).groupby("player_id", as_index=False).agg(
        recent_attempts=("attempts", "mean"), recent_carries=("carries", "mean"), recent_rush_yards=("rushing_yards", "mean")
    )
    features = features.merge(recent, on="player_id")
    features["observed_td_points"] = 4 * features["season_pass_tds"] / features["games_played"]
    features["observed_turnover_penalty"] = -2 * features["season_turnovers"] / features["games_played"]
    features["core"] = features["season_points"] - features["observed_td_points"] - features["observed_turnover_penalty"]
    features = features.merge(prior, on="player_id", how="left")

    league_td_rate = history["passing_tds"].sum() / history["attempts"].sum()
    league_to_rate = history["turnovers"].sum() / history["attempts"].sum()
    td_rate = .5 * features["prior_pass_td_rate"].fillna(league_td_rate) + .5 * league_td_rate
    to_rate = .5 * features["prior_turnover_rate"].fillna(league_to_rate) + .5 * league_to_rate
    td_signal = .25 * features["observed_td_points"] + .75 * 4 * features["recent_attempts"] * td_rate
    to_signal = .5 * features["observed_turnover_penalty"] + .5 * -2 * features["recent_attempts"] * to_rate
    features["current_signal"] = features["core"] + td_signal + to_signal
    role_anchor = features["recent_attempts"] * history["qb_points"].sum() / history["attempts"].sum()
    features["history_signal"] = features["prior_points"].where(features["prior_games"].ge(5), role_anchor)
    weight = season_weight(features["games_played"])
    features["median"] = weight * features["current_signal"] + (1 - weight) * features["history_signal"]
    features["archetype"] = np.where(
        features["prior_games"].fillna(0).lt(5), "Inexperienced",
        np.where(features["recent_carries"].ge(5) | features["recent_rush_yards"].ge(30), "Mobile", "Pocket")
    )

    starters = board.loc[
        board["position"].eq("QB") & pd.to_numeric(board["depth_order_live"], errors="coerce").eq(1)
    ][["player_id", "player", "team", "next_opponent"]].drop_duplicates("player_id")
    features = features.merge(starters, on="player_id", how="inner")
    features = features.loc[features["archetype"].eq("Mobile") & features["recent_attempts"].ge(20)].copy()
    calibration = json.loads((ROOT / "reports" / "qb-model-calibration.json").read_text(encoding="utf-8"))
    mobile = next(
        row for row in calibration["formats"]["4_point_passing_td"]["range_offsets"] if row["archetype"] == "Mobile"
    )
    features["p10"] = (features["median"] + LOWER_SCALE * float(mobile["q10"])).clip(lower=0)
    features["season"] = 2026
    features["target_week"] = target_week
    features["frozen_lower_scale"] = LOWER_SCALE
    features["starter_verified"] = True
    features["actual_points"] = np.nan
    features["below_p10"] = pd.NA
    return features[[
        "season", "target_week", "player_id", "player", "team", "next_opponent", "archetype",
        "median", "p10", "frozen_lower_scale", "starter_verified", "actual_points", "below_p10",
    ]]


def main() -> None:
    weekly = prepare(pd.read_parquet(ROOT / "data" / "raw" / "player_stats_2026_current.parquet"), 4)
    prior_data = prepare(pd.read_csv(ROOT / "data" / "raw" / "player_stats_2025.csv", low_memory=False), 4)
    prior = prior_anchors(prior_data).loc[lambda x: x["season"].eq(2026)]
    board = pd.read_parquet(ROOT / "data" / "processed" / "live_start_sit_board_current.parquet")
    completed_week = int(weekly["week"].max())
    target_week = completed_week + 1
    ledger = pd.read_csv(LEDGER) if LEDGER.exists() else pd.DataFrame()
    if not ledger.empty:
        ledger = score_existing(ledger, weekly)
    forecasts = current_forecasts(weekly, board, prior, target_week)
    if ledger.empty:
        ledger = forecasts
    else:
        existing = set(zip(ledger["target_week"], ledger["player_id"]))
        fresh = forecasts.loc[~forecasts.apply(lambda row: (row["target_week"], row["player_id"]) in existing, axis=1)]
        ledger = pd.concat([ledger, fresh], ignore_index=True)
    ledger.to_csv(LEDGER, index=False)
    evaluated = ledger.loc[ledger["actual_points"].notna()]
    summary = {
        "frozen_scale": LOWER_SCALE, "prospective_start_week": 5,
        "recorded_forecasts": int(len(ledger)), "evaluated_forecasts": int(len(evaluated)),
        "below_p10_rate": float(evaluated["below_p10"].astype(bool).mean()) if len(evaluated) else None,
        "status": "AWAITING_OUTCOMES" if len(evaluated) < 10 else "READY_FOR_REVIEW",
    }
    (ROOT / "reports" / "mobile-qb-2026-monitor.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
