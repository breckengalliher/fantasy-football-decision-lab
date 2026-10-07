"""Evaluate the user's second-round projection philosophy without deploying it."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


POSITIONS = ("QB", "RB", "WR", "TE")
TD_WEIGHTS = {"passing_tds": 4.0, "rushing_tds": 6.0, "receiving_tds": 6.0}
OPPORTUNITY_FLOORS = {"QB": 12.0, "RB": 5.0, "WR": 3.0, "TE": 2.0}


def prepare_weekly(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "season_type" in data:
        data = data.loc[data["season_type"].eq("REG")]
    data = data.loc[data["position"].isin(POSITIONS)].copy()
    numeric = ["fantasy_points_ppr", "attempts", "carries", "targets", *TD_WEIGHTS]
    for column in numeric:
        if column not in data:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    data["opportunities"] = np.where(
        data["position"].eq("QB"), data["attempts"] + data["carries"], data["carries"] + data["targets"]
    )
    data["td_points"] = sum(data[column] * weight for column, weight in TD_WEIGHTS.items())
    non_qb = ~data["position"].eq("QB")
    team_column = "recent_team" if "recent_team" in data else "team"
    skill_team_total = data.loc[non_qb].groupby(["season", "week", team_column])["opportunities"].transform("sum")
    qb_team_total = data.loc[~non_qb].groupby(["season", "week", team_column])["attempts"].transform("sum")
    data["opportunity_share"] = np.nan
    data.loc[non_qb, "opportunity_share"] = data.loc[non_qb, "opportunities"] / skill_team_total.replace(0, np.nan)
    data.loc[~non_qb, "opportunity_share"] = data.loc[~non_qb, "attempts"] / qb_team_total.replace(0, np.nan)
    return data.sort_values(["season", "week", "player_id"])


def prior_season_anchors(data: pd.DataFrame) -> pd.DataFrame:
    anchors = data.groupby(["season", "player_id", "position"], as_index=False).agg(
        prior_ppr=("fantasy_points_ppr", "mean"),
        prior_td=("td_points", "mean"),
        prior_opportunities=("opportunities", "mean"),
        prior_opportunity_share=("opportunity_share", "mean"),
    )
    position_rates = data.groupby(["season", "position"], as_index=False).agg(
        position_points=("fantasy_points_ppr", "sum"),
        position_td_points=("td_points", "sum"),
        position_opportunities=("opportunities", "sum"),
    )
    position_rates["prior_ppr_rate"] = position_rates["position_points"] / position_rates["position_opportunities"]
    position_rates["prior_td_rate"] = position_rates["position_td_points"] / position_rates["position_opportunities"]
    anchors = anchors.merge(
        position_rates[["season", "position", "prior_ppr_rate", "prior_td_rate"]],
        on=["season", "position"], how="left"
    )
    anchors["season"] += 1
    return anchors


def current_weight(games: pd.Series) -> pd.Series:
    # "Steady": history remains 40% through Week 6, then fades gradually.
    return pd.Series(np.select(
        [games.le(2), games.le(6), games.le(10)], [.40, .60, .75], default=.90
    ), index=games.index)


def build_rows(data: pd.DataFrame, round_three: bool = False) -> pd.DataFrame:
    anchors = prior_season_anchors(data)
    rows: list[pd.DataFrame] = []
    for season, season_data in data.groupby("season", sort=True):
        for week in sorted(season_data["week"].unique()):
            history = season_data.loc[season_data["week"].lt(week)].copy()
            current = season_data.loc[season_data["week"].eq(week)].copy()
            if history.empty or current.empty:
                continue
            player_history = history.sort_values(["player_id", "week"])
            features = player_history.groupby(["player_id", "position"], as_index=False).agg(
                season_ppr=("fantasy_points_ppr", "mean"),
                season_td=("td_points", "mean"),
                games_played=("fantasy_points_ppr", "size"),
            )
            recent = player_history.groupby(["player_id", "position"], as_index=False).tail(3)
            recent = recent.groupby(["player_id", "position"], as_index=False).agg(
                recent_opportunities=("opportunities", "mean"),
                recent_opportunity_share=("opportunity_share", "mean"),
            )
            features = features.merge(recent, on=["player_id", "position"])
            rates = history.groupby("position", as_index=False).agg(
                points=("fantasy_points_ppr", "sum"), td_points=("td_points", "sum"), opportunities=("opportunities", "sum")
            )
            rates["current_ppr_rate"] = rates["points"] / rates["opportunities"]
            rates["current_td_rate"] = rates["td_points"] / rates["opportunities"]
            defense = history.groupby(["opponent_team", "position"], as_index=False)["fantasy_points_ppr"].agg(["mean", "size"]).reset_index()
            league = history.groupby("position")["fantasy_points_ppr"].mean()
            defense["matchup_index"] = (
                defense["mean"] / defense["position"].map(league)
            ).clip(.90, 1.10)
            if round_three:
                # The early-season cap grows only as the defense sample matures.
                evidence_cap = min(.10, .03 + max(0, week - 5) * .01)
                reliability = (defense["size"] / 24).clip(upper=1.0)
                adjustment = (defense["matchup_index"] - 1).clip(-evidence_cap, evidence_cap) * reliability
                defense["matchup_index"] = 1 + adjustment

            current = current.merge(features, on=["player_id", "position"], how="left")
            current = current.merge(rates[["position", "current_ppr_rate", "current_td_rate"]], on="position", how="left")
            current = current.merge(anchors, on=["season", "player_id", "position"], how="left")
            current = current.merge(defense[["opponent_team", "position", "matchup_index"]], on=["opponent_team", "position"], how="left")
            current["matchup_index"] = current["matchup_index"].fillna(1.0)
            floor = current["position"].map(OPPORTUNITY_FLOORS)
            current = current.loc[current["games_played"].ge(2) & current["recent_opportunities"].ge(floor)].copy()

            # Strong TD regression: retain 25% of observed TD scoring and replace 75%
            # with the position's scoring rate at the player's current opportunity level.
            expected_td = current["recent_opportunities"] * current["current_td_rate"]
            td_regressed_production = current["season_ppr"] - current["season_td"] + .25 * current["season_td"] + .75 * expected_td
            workload_estimate = current["recent_opportunities"] * current["current_ppr_rate"]
            current["current_signal"] = .75 * td_regressed_production + .25 * workload_estimate

            prior_expected_td = current["prior_opportunities"] * current["prior_td_rate"]
            current["history_signal"] = (
                current["prior_ppr"] - current["prior_td"] + .25 * current["prior_td"] + .75 * prior_expected_td
            )
            current["history_signal"] = current["history_signal"].fillna(workload_estimate)
            weight = current_weight(current["games_played"])
            # A workload increase must be sustained and large; the cautious scenario
            # permits only a five-point acceleration in current-season weight.
            if round_three:
                # The "stay at 17" scenario requires at least five games plus both
                # historically observable role signals. Route/snap data is unavailable
                # in the backtest archive, so no override is granted from one signal.
                confirmed_role = (
                    current["games_played"].ge(5)
                    & current["prior_opportunities"].gt(0)
                    & current["recent_opportunities"].ge(1.25 * current["prior_opportunities"])
                    & current["recent_opportunity_share"].ge(1.15 * current["prior_opportunity_share"])
                )
                role_boost = .10
            else:
                confirmed_role = (
                    current["games_played"].ge(3)
                    & current["prior_opportunities"].gt(0)
                    & current["recent_opportunities"].ge(1.25 * current["prior_opportunities"])
                )
                role_boost = .05
            current["role_override"] = confirmed_role
            weight = (weight + confirmed_role.astype(float) * role_boost).clip(upper=.90)
            current["current_weight"] = weight
            base = weight * current["current_signal"] + (1 - weight) * current["history_signal"]
            current["prediction"] = base * current["matchup_index"]
            current["target_ppr"] = current["fantasy_points_ppr"]
            rows.append(current)
    return pd.concat(rows, ignore_index=True)


def metrics(rows: pd.DataFrame) -> dict:
    error = rows["target_ppr"] - rows["prediction"]
    correct = total = 0
    for _, group in rows.groupby(["season", "week", "position"]):
        predicted = group["prediction"].to_numpy()
        actual = group["target_ppr"].to_numpy()
        left, right = np.triu_indices(len(group), 1)
        usable = (predicted[left] != predicted[right]) & (actual[left] != actual[right])
        correct += int((((predicted[left] - predicted[right]) * (actual[left] - actual[right]) > 0) & usable).sum())
        total += int(usable.sum())
    return {
        "samples": int(len(rows)),
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt((error ** 2).mean())),
        "bias_actual_minus_projection": float(error.mean()),
        "correlation": float(rows["prediction"].corr(rows["target_ppr"])),
        "pairwise_ordering_accuracy": float(correct / total) if total else float("nan"),
    }


def main() -> None:
    frames = [pd.read_csv(Path(f"data/raw/player_stats_{season}.csv"), low_memory=False) for season in range(2021, 2026)]
    data = prepare_weekly(pd.concat(frames, ignore_index=True))
    rows = build_rows(data)
    round_three_rows = build_rows(data, round_three=True)
    result = {
        "model": {
            "history_fade": "steady",
            "current_signal": "75% TD-regressed production + 25% opportunity estimate",
            "touchdown_regression": "25% observed + 75% position expectation",
            "missed_games": "games played only; uncertainty widened separately",
            "matchup_cap": "plus/minus 10%",
            "role_override": "+5 percentage points current-season weight after sustained 25% opportunity increase",
        },
        "backtest_2024": metrics(rows.loc[rows["season"].eq(2024)]),
        "validation_2025": metrics(rows.loc[rows["season"].eq(2025)]),
        "round_three": {
            "notes": "Strong TD regression is relaxed only with verified scoring-role data; the historical archive lacks that field, so no exception was granted.",
            "backtest_2024": metrics(round_three_rows.loc[round_three_rows["season"].eq(2024)]),
            "validation_2025": metrics(round_three_rows.loc[round_three_rows["season"].eq(2025)]),
        },
    }
    output = Path("reports/model-round-two-results.json")
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    Path("reports/model-round-three-results.json").write_text(
        json.dumps({"round_two": {"backtest_2024": result["backtest_2024"], "validation_2025": result["validation_2025"]}, "round_three": result["round_three"]}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
