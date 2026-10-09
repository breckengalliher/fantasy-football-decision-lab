"""Validate a complete snapshot and describe one immutable Git revision.

No model calculations, provider calls, or remote writes. The workflow creates
the data commit locally, writes this pointer, then pushes both in one ref update.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
from dashboard.football_integrity import guard_forecasts

FILES = (
    "live_start_sit_board_4pt_current.parquet",
    "live_start_sit_board_6pt_current.parquet",
    "live_weekly_current.parquet",
    "live_refresh_metadata.json",
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_snapshot(directory: Path) -> dict:
    metadata = json.loads((directory / FILES[-1]).read_text(encoding="utf-8"))
    if not metadata.get("season") or not metadata.get("next_week"):
        raise ValueError("Missing season/week")
    if set(metadata.get("refreshed_qb_passing_td_formats", [])) != {4, 6}:
        raise ValueError("Incomplete scoring formats")
    counts = {}
    boards = []
    for points in (4, 6):
        filename = f"live_start_sit_board_{points}pt_current.parquet"
        board = pd.read_parquet(directory / filename)
        if board.empty or not board.columns.is_unique:
            raise ValueError("Empty or duplicate-column player board")
        required = {"player_id", "player", "team", "position", "floor_ppr", "median_ppr", "ceiling_ppr"}
        if not required <= set(board):
            raise ValueError("Incomplete player schema")
        if board.player_id.isna().any() or board.player_id.duplicated().any():
            raise ValueError("Missing or duplicate player identities")
        if board[list(required)].isna().any().any():
            raise ValueError("Missing essential player fields")
        invalid = ~guard_forecasts(board).forecast_valid
        if invalid.any():
            # Retain diagnostic baselines only when explicitly quarantined.
            # Missing flags or truthy/string flags never authorize publication.
            required_flags = {"forecast_valid", "forecast_status", "is_roster_relevant"}
            if not required_flags <= set(board):
                raise ValueError("Football forecast validation failed; publication blocked")
            rejected = board.loc[invalid]
            explicit_false = lambda v: isinstance(v, (bool, np.bool_)) and not v
            if (not rejected.forecast_valid.map(explicit_false).all()
                    or not rejected.is_roster_relevant.map(explicit_false).all()
                    or not rejected.forecast_status.eq("Unavailable: invalid forecast; verification needed").all()):
                raise ValueError("Football forecast validation failed; publication blocked")
        counts[filename] = len(board)
        boards.append(board)
    identity_columns = ["player_id", "player", "team", "position"]
    if not boards[0][identity_columns].sort_values("player_id").reset_index(drop=True).equals(
        boards[1][identity_columns].sort_values("player_id").reset_index(drop=True)
    ):
        raise ValueError("Scoring snapshots disagree on player identities")
    weekly = pd.read_parquet(directory / FILES[2])
    if weekly.empty:
        raise ValueError("Empty historical statistics")
    counts[FILES[2]] = len(weekly)
    return {"metadata": metadata, "record_counts": counts}


def build_manifest(directory: Path, revision: str, now: datetime | None = None) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Publication must reference a full immutable Git commit")
    validation = validate_snapshot(directory)
    metadata = validation["metadata"]
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    files = {filename: {"sha256": digest((directory / filename).read_bytes()),
                       "record_count": validation["record_counts"].get(filename)}
             for filename in FILES}
    version = digest(json.dumps(files, sort_keys=True).encode())
    return {
        "schema_version": 1, "version": version, "revision": revision,
        "season": metadata["season"], "week": metadata["next_week"],
        "validation_status": "passed", "validated_at": timestamp,
        # This is pointer preparation, not proof that a Git push succeeded.
        "prepared_at": timestamp, "files": files,
        "projection_source_retrieved_at": metadata.get("refreshed_at"),
        "availability_source_retrieved_at": metadata.get("injury_refreshed_at"),
        "availability_source_updated_at": metadata.get("injury_source_updated_at"),
        "depth_source_updated_at": metadata.get("depth_source_updated_at"),
        "source_freshness": {
            "injury": "verified" if metadata.get("injury_freshness_verified") is True else "unverified",
            "depth": "verified" if metadata.get("depth_freshness_verified") is True else "unverified",
        },
    }


def write_manifest(directory: Path, revision: str) -> dict:
    manifest = build_manifest(directory, revision)
    pointer = directory / "publication_manifest.json"
    temporary = pointer.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(pointer)
    return manifest


def verify_file(payload: bytes, manifest: dict, filename: str) -> None:
    if manifest.get("validation_status") != "passed":
        raise ValueError("Unvalidated publication")
    if digest(payload) != manifest["files"][filename]["sha256"]:
        raise ValueError("Published file does not match its validated version")
