"""Pure change detection and review helpers for read-only Sleeper synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class SyncDiff:
    roster_added: tuple[str, ...]
    roster_removed: tuple[str, ...]
    starters_added: tuple[str, ...]
    starters_removed: tuple[str, ...]
    bench_added: tuple[str, ...]
    bench_removed: tuple[str, ...]
    league_changes: dict[str, dict[str, Any]]
    identity_changed: bool
    unmatched: tuple[str, ...]
    local_lineup_conflict: bool

    @property
    def roster_changed(self) -> bool:
        return bool(self.roster_added or self.roster_removed)

    @property
    def lineup_changed(self) -> bool:
        # Bench membership naturally changes when a player is added or dropped;
        # only a change to the starter set is an actual Sleeper lineup change.
        return bool(self.starters_added or self.starters_removed)

    @property
    def has_changes(self) -> bool:
        return bool(self.roster_changed or self.lineup_changed or self.league_changes or self.identity_changed or self.unmatched)

    def as_dict(self) -> dict[str, Any]:
        return {
            "roster_added": list(self.roster_added),
            "roster_removed": list(self.roster_removed),
            "starters_added": list(self.starters_added),
            "starters_removed": list(self.starters_removed),
            "bench_added": list(self.bench_added),
            "bench_removed": list(self.bench_removed),
            "league_changes": self.league_changes,
            "identity_changed": self.identity_changed,
            "unmatched": list(self.unmatched),
            "local_lineup_conflict": self.local_lineup_conflict,
            "roster_changed": self.roster_changed,
            "lineup_changed": self.lineup_changed,
            "has_changes": self.has_changes,
        }


def _ids(snapshot: dict[str, Any] | None, field: str) -> set[str]:
    return {str(value) for value in (snapshot or {}).get(field, []) if value}


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Stable source hash that ignores API ordering and fetch timestamps."""
    payload = {
        "owner_id": str(snapshot.get("owner_id") or ""),
        "roster_id": str(snapshot.get("roster_id") or ""),
        "players": sorted(_ids(snapshot, "players")),
        "starters": sorted(_ids(snapshot, "starters")),
        "roster_positions": sorted(str(value) for value in snapshot.get("roster_positions", []) if value),
        "scoring_settings": {str(key): snapshot.get("scoring_settings", {}).get(key) for key in sorted(snapshot.get("scoring_settings", {}))},
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def build_snapshot(roster: dict[str, Any], league: Any, mappings: list[dict[str, Any]]) -> dict[str, Any]:
    players = sorted({str(value) for value in roster.get("players") or [] if value})
    starters = sorted({str(value) for value in roster.get("starters") or [] if value})
    snapshot = {
        "schema_version": 1,
        "owner_id": str(roster.get("owner_id") or ""),
        "roster_id": str(roster.get("roster_id") or ""),
        "team_name": str((roster.get("metadata") or {}).get("team_name") or ""),
        "league_id": str(getattr(league, "league_id", "")),
        "league_name": str(getattr(league, "name", "Sleeper league")),
        "season": int(getattr(league, "season", 0) or 0),
        "players": players,
        "starters": starters,
        "bench": sorted(set(players) - set(starters)),
        "roster_positions": [str(value) for value in getattr(league, "roster_positions", ())],
        "scoring_settings": dict(getattr(league, "scoring_settings", {}) or {}),
        "mappings": mappings,
        "unmatched": [record for record in mappings if not record.get("matched")],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    snapshot["source_hash"] = snapshot_hash(snapshot)
    return snapshot


def detect_changes(previous: dict[str, Any] | None, latest: dict[str, Any], local_starters: set[str] | None = None) -> SyncDiff:
    previous_players, latest_players = _ids(previous, "players"), _ids(latest, "players")
    previous_starters, latest_starters = _ids(previous, "starters"), _ids(latest, "starters")
    previous_bench, latest_bench = previous_players - previous_starters, latest_players - latest_starters
    keys = ("roster_positions", "scoring_settings")
    league_changes = {
        key: {"before": (previous or {}).get(key), "after": latest.get(key)}
        for key in keys
        if previous is not None and (previous or {}).get(key) != latest.get(key)
    }
    mapped_starters = {
        str(record["player_id"])
        for record in latest.get("mappings", [])
        if record.get("matched") and str(record.get("external_player_id")) in latest_starters
    }
    local_conflict = local_starters is not None and set(local_starters) != mapped_starters
    return SyncDiff(
        roster_added=tuple(sorted(latest_players - previous_players)),
        roster_removed=tuple(sorted(previous_players - latest_players)),
        starters_added=tuple(sorted(latest_starters - previous_starters)),
        starters_removed=tuple(sorted(previous_starters - latest_starters)),
        bench_added=tuple(sorted(latest_bench - previous_bench)),
        bench_removed=tuple(sorted(previous_bench - latest_bench)),
        league_changes=league_changes,
        identity_changed=bool(previous and (str(previous.get("owner_id")) != str(latest.get("owner_id")) or str(previous.get("roster_id")) != str(latest.get("roster_id")))),
        unmatched=tuple(str(record.get("external_player_id")) for record in latest.get("unmatched", [])),
        local_lineup_conflict=local_conflict,
    )


def external_name(snapshot: dict[str, Any], external_id: str) -> str:
    record = next((row for row in snapshot.get("mappings", []) if str(row.get("external_player_id")) == str(external_id)), None)
    return str((record or {}).get("name") or external_id)


def local_starter_ids(roster: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for slot in roster:
        assignment = slot.get("roster_assignments") or []
        assignment = assignment[0] if isinstance(assignment, list) and assignment else assignment
        if slot.get("is_starter") and isinstance(assignment, dict) and assignment.get("player_id"):
            result.add(str(assignment["player_id"]))
    return result
