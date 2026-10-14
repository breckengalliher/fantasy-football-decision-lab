"""Fantasy scoring and basic receiving metric helpers."""

from __future__ import annotations

import pandas as pd


def calculate_receiving_ppr_points(
    receptions: pd.Series,
    receiving_yards: pd.Series,
    receiving_touchdowns: pd.Series,
) -> pd.Series:
    """Calculate full-PPR points from receiving production.

    Each reception is worth 1 point, each receiving yard is worth 0.1
    points, and each receiving touchdown is worth 6 points.
    """

    return receptions + (0.1 * receiving_yards) + (6 * receiving_touchdowns)


def safe_rate(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide two series and return missing values when the denominator is zero."""

    return numerator.div(denominator.where(denominator.ne(0)))


def add_basic_receiving_metrics(player_weeks: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with beginner-friendly fantasy and efficiency metrics."""

    required_columns = {
        "receptions",
        "receiving_yards",
        "receiving_tds",
        "targets",
        "receiving_air_yards",
    }
    missing_columns = required_columns.difference(player_weeks.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns: {missing}")

    enriched = player_weeks.copy()
    enriched["ppr_receiving_points"] = calculate_receiving_ppr_points(
        enriched["receptions"],
        enriched["receiving_yards"],
        enriched["receiving_tds"],
    )
    enriched["catch_rate"] = safe_rate(enriched["receptions"], enriched["targets"])
    enriched["yards_per_target"] = safe_rate(
        enriched["receiving_yards"], enriched["targets"]
    )
    enriched["average_depth_of_target"] = safe_rate(
        enriched["receiving_air_yards"], enriched["targets"]
    )
    enriched["ppr_points_per_target"] = safe_rate(
        enriched["ppr_receiving_points"], enriched["targets"]
    )
    return enriched
