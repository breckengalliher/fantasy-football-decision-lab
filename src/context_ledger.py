"""Append-only point-in-time archive for volatile role and availability context."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


CONTEXT_FIELDS = (
    "player_id", "player", "team", "position", "next_opponent",
    "injury_status_live", "practice_status_live", "injury_body_part_live",
    "injury_note_live", "injury_updated_live", "injury_source_live",
    "injury_conflict_live", "injury_checked_at", "depth_position_live",
    "depth_order_live", "latest_snap_pct", "recent_snap_pct", "snap_week",
)


def build_context_snapshot(
    board: pd.DataFrame,
    *,
    season: int,
    week: int,
    captured_at: str,
) -> pd.DataFrame:
    """Capture only genuinely observed point-in-time fields without imputation."""
    eligible = board.copy()
    if "is_roster_relevant" in eligible:
        eligible = eligible.loc[eligible["is_roster_relevant"].fillna(False)]
    result = pd.DataFrame(index=eligible.index)
    for field in CONTEXT_FIELDS:
        result[field] = eligible[field] if field in eligible else pd.NA
    result.insert(0, "captured_at", captured_at)
    result.insert(1, "season", int(season))
    result.insert(2, "week", int(week))
    result["routes_available"] = False
    result["first_read_share_available"] = False
    result["collection_note"] = (
        "Injury, practice, depth and snap fields are archived as observed. "
        "Routes and first-read share are not supplied by the current providers."
    )
    return result.reset_index(drop=True)


def append_context_snapshot(snapshot: pd.DataFrame, root: Path) -> Path:
    if snapshot.empty:
        raise ValueError("Refusing to publish an empty context snapshot.")
    first = snapshot.iloc[0]
    timestamp = str(first["captured_at"]).replace(":", "-").replace("+", "_")
    target = (
        Path(root) / f"season={int(first['season'])}" / f"week={int(first['week'])}"
        / f"{timestamp}.parquet"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Context ledger entries are immutable: {target}")
    temporary = target.with_suffix(".parquet.tmp")
    snapshot.to_parquet(temporary, index=False)
    temporary.replace(target)
    return target
