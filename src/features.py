"""Time-safe feature engineering for wide-receiver player weeks."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


ROLLING_METRICS = ["target_share", "air_yards_share", "fantasy_points_ppr"]


def add_previous_game_features(
    receiver_weeks: pd.DataFrame,
    windows: Iterable[int] = (1, 3, 5),
) -> pd.DataFrame:
    """Add shifted rolling averages based on previous games played.

    A listed zero-target appearance remains a game played and contributes zero
    target share and zero air-yard share. Rolling histories restart each season
    and never include the game represented by the current row.
    """

    required = {"player_id", "season", "week", *ROLLING_METRICS}
    missing = required.difference(receiver_weeks.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    result = receiver_weeks.sort_values(
        ["player_id", "season", "week"]
    ).reset_index(drop=True).copy()
    player_seasons = result.groupby(["player_id", "season"], sort=False)

    for metric in ROLLING_METRICS:
        previous_values = player_seasons[metric].shift(1)
        result[f"previous_game_{metric}"] = previous_values

        for window in windows:
            if window == 1:
                result[f"rolling_{window}_{metric}"] = previous_values
            else:
                result[f"rolling_{window}_{metric}"] = (
                    previous_values.groupby(
                        [result["player_id"], result["season"]], sort=False
                    )
                    .rolling(window=window, min_periods=window)
                    .mean()
                    .reset_index(level=[0, 1], drop=True)
                    .sort_index()
                    .round(10)
                )

    result["games_previously_recorded"] = player_seasons.cumcount()
    return result


def add_early_season_fallback_features(
    receiver_weeks: pd.DataFrame,
    window: int = 5,
) -> pd.DataFrame:
    """Add cross-season five-appearance features and dashboard confidence labels."""

    required = {"player_id", "season", "week", "team", *ROLLING_METRICS}
    missing = required.difference(receiver_weeks.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    result = receiver_weeks.sort_values(
        ["player_id", "season", "week"]
    ).reset_index(drop=True).copy()
    players = result.groupby("player_id", sort=False)

    for metric in ROLLING_METRICS:
        previous_values = players[metric].shift(1)
        result[f"fallback_rolling_{window}_{metric}"] = (
            previous_values.groupby(result["player_id"], sort=False)
            .rolling(window=window, min_periods=window)
            .mean()
            .reset_index(level=0, drop=True)
            .sort_index()
        )

    result["career_appearances_previously_recorded"] = players.cumcount()
    result["previous_appearance_team"] = players["team"].shift(1)
    result["changed_team_since_previous_appearance"] = (
        result["previous_appearance_team"].notna()
        & result["team"].ne(result["previous_appearance_team"])
    )

    previous_seasons = players["season"].shift(1)
    earliest_history_season = (
        previous_seasons.groupby(result["player_id"], sort=False)
        .rolling(window=window, min_periods=window)
        .min()
        .reset_index(level=0, drop=True)
        .sort_index()
    )
    result["fallback_history_crosses_offseason"] = (
        earliest_history_season.notna() & earliest_history_season.lt(result["season"])
    )

    complete_history = result["career_appearances_previously_recorded"].ge(window)
    result["dashboard_confidence"] = "low"
    result.loc[
        result["career_appearances_previously_recorded"].eq(0),
        "dashboard_confidence",
    ] = "unavailable"
    result.loc[complete_history, "dashboard_confidence"] = "normal"
    result.loc[
        complete_history & result["fallback_history_crosses_offseason"],
        "dashboard_confidence",
    ] = "reduced"
    result.loc[
        result["changed_team_since_previous_appearance"],
        "dashboard_confidence",
    ] = "low"
    return result
