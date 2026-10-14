"""Append-only storage for published projections and later game outcomes.

The ledger is deliberately separate from the mutable ``*_current`` snapshots.
Every publication creates a new immutable parquet file; an existing snapshot is
never rewritten.  Actual outcomes live in a separate namespace so forecast
records cannot be contaminated by postgame information.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd


FORECAST_COLUMNS = (
    "snapshot_id", "forecast_timestamp", "information_cutoff", "season", "week",
    "player_id", "player", "team", "position", "next_opponent", "scoring_format",
    "model_version", "expected_points", "median", "interval_lower", "interval_upper",
    "input_data_version", "availability_scenario",
)


def frame_fingerprint(frame: pd.DataFrame, columns: tuple[str, ...] | None = None) -> str:
    """Return a stable, compact identifier for the inputs used by a forecast."""
    selected = frame.loc[:, [c for c in (columns or tuple(frame.columns)) if c in frame]].copy()
    selected = selected.sort_index(axis=1).sort_values(list(selected.columns), kind="stable")
    payload = pd.util.hash_pandas_object(selected, index=False).values.tobytes()
    return hashlib.sha256(payload).hexdigest()[:16]


def build_forecast_snapshot(
    board: pd.DataFrame,
    *,
    season: int,
    week: int,
    scoring_format: str,
    model_version: str,
    forecast_timestamp: str | None = None,
    information_cutoff: str | None = None,
    input_data_version: str | None = None,
    snapshot_id: str | None = None,
) -> pd.DataFrame:
    """Normalize a published board into the immutable ledger schema."""
    timestamp = forecast_timestamp or datetime.now(timezone.utc).isoformat()
    cutoff = information_cutoff or timestamp
    identifier = snapshot_id or f"{season}-W{week}-{uuid4().hex[:12]}"
    version = input_data_version or frame_fingerprint(
        board,
        ("player_id", "games_played", "season_ppr", "recent_ppr", "recent_opportunities", "median_ppr"),
    )
    eligible = board.copy()
    if "is_roster_relevant" in eligible:
        eligible = eligible.loc[eligible["is_roster_relevant"].fillna(False)]
    if "next_opponent" in eligible:
        eligible = eligible.loc[eligible["next_opponent"].notna()]
    result = pd.DataFrame({
        "snapshot_id": identifier,
        "forecast_timestamp": timestamp,
        "information_cutoff": cutoff,
        "season": int(season),
        "week": int(week),
        "player_id": eligible.get("player_id"),
        "player": eligible.get("player"),
        "team": eligible.get("team"),
        "position": eligible.get("position"),
        "next_opponent": eligible.get("next_opponent"),
        "scoring_format": scoring_format,
        "model_version": model_version,
        "expected_points": eligible.get("projected_ppr", eligible.get("median_ppr")),
        "median": eligible.get("median_ppr", eligible.get("projected_ppr")),
        "interval_lower": eligible.get("floor_ppr"),
        "interval_upper": eligible.get("ceiling_ppr"),
        "input_data_version": version,
        "availability_scenario": eligible.get("injury_status_live", pd.Series("baseline", index=eligible.index)).fillna("baseline"),
    })
    return result.loc[:, FORECAST_COLUMNS].reset_index(drop=True)


def append_forecast_snapshot(snapshot: pd.DataFrame, root: Path) -> Path:
    """Write a new ledger file and fail closed if its target already exists."""
    missing = set(FORECAST_COLUMNS) - set(snapshot.columns)
    if missing:
        raise ValueError(f"Forecast snapshot is missing columns: {sorted(missing)}")
    if snapshot.empty:
        raise ValueError("Refusing to publish an empty projection ledger snapshot.")
    identity = snapshot.iloc[0]
    timestamp = str(identity["forecast_timestamp"]).replace(":", "-").replace("+", "_")
    destination = (
        Path(root) / "projections" / f"season={int(identity['season'])}"
        / f"week={int(identity['week'])}"
        / f"{timestamp}_{identity['scoring_format']}_{identity['snapshot_id']}.parquet"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Projection ledger entries are immutable: {destination}")
    temporary = destination.with_suffix(".parquet.tmp")
    snapshot.to_parquet(temporary, index=False)
    temporary.replace(destination)
    return destination


def write_manifest(paths: list[Path], *, root: Path, metadata: dict) -> Path:
    """Write an immutable publication manifest adjacent to its snapshots."""
    manifest_id = metadata.get("publication_id") or uuid4().hex
    target = Path(root) / "manifests" / f"{manifest_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Ledger manifests are immutable: {target}")
    payload = {**metadata, "publication_id": manifest_id, "forecast_files": [str(p) for p in paths]}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
