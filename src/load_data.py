"""Load and validate nflverse weekly wide-receiver data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


KEY_COLUMNS = ["player_id", "season", "week", "season_type"]


def load_player_stats(data_directory: str | Path) -> pd.DataFrame:
    """Load all downloaded player-stat CSV files into one table."""

    paths = sorted(Path(data_directory).glob("player_stats_*.csv"))
    if not paths:
        raise FileNotFoundError(f"No player_stats CSV files found in {data_directory}")

    frames = [pd.read_csv(path, low_memory=False) for path in paths]
    return pd.concat(frames, ignore_index=True)


def select_regular_season_receivers(player_stats: pd.DataFrame) -> pd.DataFrame:
    """Select regular-season rows for players listed as wide receivers."""

    receivers = player_stats.loc[
        player_stats["season_type"].eq("REG") & player_stats["position"].eq("WR")
    ].copy()
    return receivers.sort_values(["player_id", "season", "week"]).reset_index(drop=True)


def validate_receiver_keys(receivers: pd.DataFrame) -> None:
    """Raise an error when the intended player-week key is missing or duplicated."""

    missing = set(KEY_COLUMNS).difference(receivers.columns)
    if missing:
        raise ValueError(f"Missing key columns: {', '.join(sorted(missing))}")
    if receivers.duplicated(KEY_COLUMNS).any():
        raise ValueError("Duplicate player-season-week rows found")
