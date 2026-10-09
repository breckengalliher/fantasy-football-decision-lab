"""Generate non-production regularized challenger forecasts for shadow testing."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model_round_two import build_rows, prepare_weekly


PROCESSED = ROOT / "data" / "processed"
SHADOW = ROOT / "data" / "shadow_ledger"
POSITIONS = ("QB", "RB", "WR", "TE")
NUMERIC_FEATURES = [
    "games_played", "season_ppr", "season_td", "recent_opportunities",
    "recent_opportunity_share", "prior_ppr", "prior_opportunities",
    "prior_opportunity_share", "current_ppr_rate", "current_td_rate", "matchup_index",
]


def fit_ridge(rows: pd.DataFrame, alpha: float = 100.0) -> dict:
    medians = rows[NUMERIC_FEATURES].apply(pd.to_numeric, errors="coerce").median()
    clean = rows[NUMERIC_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(medians)
    means = clean.mean()
    scales = clean.std().replace(0, 1).fillna(1)
    positions = pd.get_dummies(rows["position"], dtype=float).reindex(columns=POSITIONS, fill_value=0.0)
    matrix = np.column_stack([np.ones(len(rows)), positions.to_numpy(), ((clean - means) / scales).to_numpy()])
    penalty = np.eye(matrix.shape[1]) * alpha
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(matrix.T @ matrix + penalty, matrix.T @ rows["target_ppr"].to_numpy(dtype=float))
    return {
        "alpha": alpha,
        "medians": medians.to_dict(), "means": means.to_dict(), "scales": scales.to_dict(),
        "coefficients": coefficients.tolist(),
    }


def ridge_predict(rows: pd.DataFrame, model: dict) -> np.ndarray:
    medians = pd.Series(model["medians"])
    means = pd.Series(model["means"])
    scales = pd.Series(model["scales"])
    clean = rows[NUMERIC_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(medians)
    positions = pd.get_dummies(rows["position"], dtype=float).reindex(columns=POSITIONS, fill_value=0.0)
    matrix = np.column_stack([np.ones(len(rows)), positions.to_numpy(), ((clean - means) / scales).to_numpy()])
    return matrix @ np.asarray(model["coefficients"])


def live_feature_rows(board: pd.DataFrame, weekly: pd.DataFrame, prior_weekly: pd.DataFrame) -> pd.DataFrame:
    current = prepare_weekly(weekly)
    prior = prepare_weekly(prior_weekly)
    player_column = "player_id"
    features = current.groupby([player_column, "position"], as_index=False).agg(
        season_ppr=("fantasy_points_ppr", "mean"), season_td=("td_points", "mean"),
        games_played=("fantasy_points_ppr", "size"),
    )
    recent = current.sort_values([player_column, "week"]).groupby([player_column, "position"], as_index=False).tail(3)
    recent = recent.groupby([player_column, "position"], as_index=False).agg(
        recent_opportunities=("opportunities", "mean"),
        recent_opportunity_share=("opportunity_share", "mean"),
    )
    features = features.merge(recent, on=[player_column, "position"], how="left")
    anchors = prior.groupby([player_column, "position"], as_index=False).agg(
        prior_ppr=("fantasy_points_ppr", "mean"), prior_opportunities=("opportunities", "mean"),
        prior_opportunity_share=("opportunity_share", "mean"),
    )
    rates = current.groupby("position", as_index=False).agg(
        points=("fantasy_points_ppr", "sum"), td_points=("td_points", "sum"), opportunities=("opportunities", "sum")
    )
    rates["current_ppr_rate"] = rates["points"] / rates["opportunities"].replace(0, np.nan)
    rates["current_td_rate"] = rates["td_points"] / rates["opportunities"].replace(0, np.nan)
    defense = current.groupby(["opponent_team", "position"], as_index=False)["fantasy_points_ppr"].mean()
    league = current.groupby("position")["fantasy_points_ppr"].mean()
    defense["matchup_index"] = (defense["fantasy_points_ppr"] / defense["position"].map(league)).clip(.90, 1.10)
    identity = board[["player_id", "player", "team", "position", "next_opponent", "median_ppr"]].drop_duplicates("player_id")
    result = identity.merge(features, on=["player_id", "position"], how="left")
    result = result.merge(anchors, on=["player_id", "position"], how="left")
    result = result.merge(rates[["position", "current_ppr_rate", "current_td_rate"]], on="position", how="left")
    result = result.merge(
        defense[["opponent_team", "position", "matchup_index"]],
        left_on=["next_opponent", "position"], right_on=["opponent_team", "position"], how="left",
    )
    result["matchup_index"] = result["matchup_index"].fillna(1.0)
    return result


def append_shadow_snapshot(frame: pd.DataFrame, *, season: int, week: int, timestamp: str) -> Path:
    target = SHADOW / f"season={season}" / f"week={week}" / f"{timestamp.replace(':', '-').replace('+', '_')}.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Shadow forecasts are immutable: {target}")
    temporary = target.with_suffix(".parquet.tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(target)
    return target


def main() -> None:
    metadata = json.loads((PROCESSED / "live_refresh_metadata.json").read_text(encoding="utf-8"))
    historical = []
    for season in range(2021, int(metadata["season"])):
        path = ROOT / "data" / "raw" / f"player_stats_{season}.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"Shadow training requires {path}. Run in the research environment with historical inputs; "
                "production serving must not train this model."
            )
        historical.append(pd.read_csv(path, low_memory=False))
    history = prepare_weekly(pd.concat(historical, ignore_index=True))
    training_rows = build_rows(history, round_three=True)
    model = fit_ridge(training_rows, alpha=100.0)
    board = pd.read_parquet(PROCESSED / "live_start_sit_board_4pt_current.parquet")
    board = board.loc[
        board["is_roster_relevant"].fillna(False)
        & board["position"].isin(POSITIONS)
        & board["next_opponent"].notna()
    ].copy()
    weekly = pd.read_parquet(PROCESSED / "live_weekly_current.parquet")
    prior = historical[-1]
    live = live_feature_rows(board, weekly, prior)
    live["shadow_projected_ppr"] = ridge_predict(live, model)
    live["incumbent_projected_ppr"] = live["median_ppr"]
    live["shadow_minus_incumbent"] = live["shadow_projected_ppr"] - live["incumbent_projected_ppr"]
    live["forecast_timestamp"] = datetime.now(timezone.utc).isoformat()
    live["information_cutoff"] = metadata["refreshed_at"]
    live["model_version"] = "regularized-opportunity-efficiency-shadow-v1"
    live["scoring_format"] = "FULL-PPR-4PT-PASS-TD"
    output = live[[
        "forecast_timestamp", "information_cutoff", "model_version", "scoring_format",
        "player_id", "player", "team", "position", "next_opponent",
        "shadow_projected_ppr", "incumbent_projected_ppr", "shadow_minus_incumbent",
    ]]
    path = append_shadow_snapshot(
        output, season=int(metadata["season"]), week=int(metadata["next_week"]),
        timestamp=str(output["forecast_timestamp"].iloc[0]),
    )
    print(json.dumps({"path": str(path), "forecasts": len(output), "production_effect": "none"}))


if __name__ == "__main__":
    main()
