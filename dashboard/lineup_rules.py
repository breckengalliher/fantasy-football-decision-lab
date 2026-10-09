"""Deterministic Sunday Command Center readiness and action rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from dashboard.availability import UNAVAILABLE, status_key


UNCERTAIN = {"questionable", "doubtful"}


@dataclass(frozen=True)
class LineupAction:
    player_id: str | None
    slot_type: str
    severity: str
    mandatory: bool
    headline: str
    explanation: str
    kickoff_at: datetime | None
    estimated_impact: float = 0.0


def _utc(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def critical_data_fresh(metadata: dict[str, Any], now: datetime, *, projection_hours: int = 24, context_hours: int = 4) -> bool:
    projection = _utc(metadata.get("refreshed_at"))
    context = _utc(metadata.get("context_refreshed_at") or metadata.get("injury_refreshed_at"))
    return bool(
        projection and context
        # Retrieval timestamps alone cannot establish report freshness.
        and metadata.get("injury_freshness_verified") is True
        and metadata.get("depth_freshness_verified") is True
        and timedelta(0) <= now.astimezone(timezone.utc) - projection <= timedelta(hours=projection_hours)
        and timedelta(0) <= now.astimezone(timezone.utc) - context <= timedelta(hours=context_hours)
    )


def build_lineup_actions(starters: Iterable[dict[str, Any]], now: datetime) -> list[LineupAction]:
    actions: list[LineupAction] = []
    current = now.astimezone(timezone.utc)
    for starter in starters:
        slot = str(starter.get("slot_type", ""))
        player_id = starter.get("player_id")
        kickoff = _utc(starter.get("kickoff_at"))
        started = game_has_started(starter, current)
        status = status_key(starter.get("availability", ""))
        if not player_id:
            actions.append(LineupAction(None, slot, "urgent", True, f"Empty {slot} slot", "Add an eligible player before this lineup slot locks.", kickoff))
            continue
        if bool(starter.get("bye_week", False)):
            actions.append(LineupAction(str(player_id), slot, "urgent", True, "Starter is on bye", "Move this player out of the starting lineup.", kickoff))
            continue
        if status in UNAVAILABLE:
            explanation = "The player is confirmed unavailable."
            if started:
                explanation += " The lineup slot is already locked."
            actions.append(LineupAction(str(player_id), slot, "urgent", True, "Starter unavailable", explanation, kickoff))
            continue
        if status in UNCERTAIN and not started:
            hours = (kickoff - current).total_seconds() / 3600 if kickoff else 999
            severity = "urgent" if status == "doubtful" or hours <= 2 else "attention"
            actions.append(LineupAction(str(player_id), slot, severity, False, f"Starter is {status}", "Verify the official inactive list and prepare an eligible replacement.", kickoff))
    return sorted(
        actions,
        key=lambda action: (
            not action.mandatory,
            0 if action.severity == "urgent" else 1,
            action.kickoff_at or datetime.max.replace(tzinfo=timezone.utc),
            -action.estimated_impact,
        ),
    )


def game_has_started(player: dict[str, Any], now: datetime) -> bool:
    """Explicit postponements override an old scheduled kickoff timestamp."""
    status = str(player.get("game_status_live", "")).strip().casefold()
    if status in {"postponed", "rescheduled", "cancelled", "canceled"}:
        return False
    kickoff = _utc(player.get("kickoff_at"))
    return status in {"in progress", "final", "closed"} or bool(player.get("game_started")) or bool(kickoff and kickoff <= now.astimezone(timezone.utc))


def lineup_status(starters: Iterable[dict[str, Any]], metadata: dict[str, Any], now: datetime) -> str:
    starters = list(starters)
    if not starters or any(not player.get("player_id") for player in starters):
        return "INCOMPLETE SETUP"
    if not critical_data_fresh(metadata, now):
        return "VERIFY DATA"
    if any(status_key(p.get('game_status_live')) in {'postponed','rescheduled','cancelled','canceled'} for p in starters):
        return "VERIFY DATA"
    if any(player.get("data_unavailable") or (not _utc(player.get("kickoff_at")) and not player.get("bye_week")) for player in starters):
        return "VERIFY DATA"
    actions = build_lineup_actions(starters, now)
    if any(action.mandatory for action in actions):
        return "ACTION REQUIRED"
    if actions:
        return "INJURY CONCERN"
    if any(game_has_started(player, now) for player in starters):
        return "GAME IN PROGRESS"
    return "READY"

