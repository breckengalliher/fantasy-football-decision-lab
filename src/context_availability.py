"""Preserve reviewed availability authority during a supplemental context refresh.

Retrieval is not certification. Existing source receipts and timestamps survive;
only clock-driven expiration can downgrade claims. New/changed identities require
a new reviewed certificate, not inferred coverage from a successful provider GET.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone

from dashboard.availability_evidence import resolve_availability, timestamp
from src.availability_certificate import validate_certificate

REVIEWED_COLUMNS = (
    "injury_record_live", "injury_status_live", "practice_status_live",
    "injury_body_part_live", "injury_note_live", "injury_updated_live",
    "injury_source_live", "injury_conflict_live", "injury_checked_at",
    "depth_position_live", "depth_order_live", "game_status_live",
    "bye_week", "next_opponent", "gameday", "gametime", "kickoff_at",
)

def retain_reviewed_availability(boards, originals, metadata, now=None):
    now = now or datetime.now(timezone.utc)
    certificate = metadata.get("availability_certificate")
    if certificate is None:
        return boards, metadata
    metadata = deepcopy(metadata)
    certificate = metadata["availability_certificate"]
    retained = {}
    for points, board in boards.items():
        original = originals[points].set_index("player_id")
        if (set(board.player_id) != set(original.index) or not original.index.is_unique
                or board.player_id.duplicated().any()):
            raise ValueError("Reviewed availability requires unchanged player identities")
        result = board.copy()
        for field in ("player", "team", "position", "is_roster_relevant"):
            if not result[field].equals(result.player_id.map(original[field]).rename(field)):
                raise ValueError("Reviewed availability identity or scope changed")
        for column in REVIEWED_COLUMNS:
            if column in original:
                result[column] = result.player_id.map(original[column])
            else:
                result[column] = None
        retained[points] = result

    if certificate.get("schema_version") == 2:
        if certificate.get("policy") != "all_availability_actions_blocked":
            raise ValueError("Unrecognized restricted availability policy")
        for record in certificate["players"]:
            game = record["game"]
            inactive = record["inactives"]
            due = timestamp(inactive.get("due_at"))
            if inactive.get("state") == "not_yet_due" and due and now >= due:
                inactive["state"] = "due_missing"
                record["blockers"] = list(dict.fromkeys([
                    *record.get("blockers", []), "Due game-day inactive report missing"]))
            resolved = resolve_availability(record.get("events", []),
                player_id=record["player_id"], team=record["team"],
                game_id=game.get("game_id"), kickoff_at=game.get("kickoff_at"), now=now,
                game_status=game.get("status", "scheduled"), bye=game.get("bye", False))
            record.update(availability=resolved["availability"], resolved=resolved,
                          recommendation_allowed=False)
            if resolved["game_state"] in {"bye", "started", "final", "postponed"}:
                record["classification"] = "OUTSIDE ACTIONABLE SCOPE"
            elif (record["classification"] == "VERIFIED" and resolved["availability"] == "Unknown") or (
                    record["classification"] == "PENDING OFFICIAL REPORT" and inactive.get("state") == "due_missing"):
                record["classification"] = "UNKNOWN"
            # Never upgrade a classification from this general-context fetch.
            for board in retained.values():
                selected = board.player_id.eq(record["player_id"])
                board.loc[selected, "injury_status_live"] = resolved["availability"]
                if resolved["availability"] == "Unknown" and "injury_note_live" in board:
                    board.loc[selected, "injury_note_live"] = "Availability unverified; no new official report established by context retrieval."
        certificate["reevaluated_at"] = now.isoformat()
        counts = Counter(r["classification"] for r in certificate["players"])
        coverage = metadata.setdefault("availability_coverage", {})
        coverage.update(evaluated_at=now.isoformat(), classifications=dict(counts),
            eligible_forecast_players=len(certificate["players"]),
            actionable_time_scope_players=sum(r["classification"] != "OUTSIDE ACTIONABLE SCOPE" for r in certificate["players"]),
            pending_official_reports=counts["PENDING OFFICIAL REPORT"],
            verified_unavailable_statuses=sum(r["availability"] not in {"Unknown", "Available", "Questionable", "Doubtful"} for r in certificate["players"]),
            unknown_status_rows=sum(r["availability"] == "Unknown" for r in certificate["players"]),
            blocked_from_actionable_recommendations=len(certificate["players"]),
            fully_verified_availability=False)
    # Schema 1 must remain fully valid. Expiration or mismatches block delivery;
    # this refresh cannot silently downgrade a verified release policy.
    validation = validate_certificate(certificate, list(retained.values()), metadata, now)
    metadata["general_context_availability_policy"] = {
        "reviewed_sources_retained": True, "source_timestamps_advanced": False,
        "reevaluated_at": now.isoformat(), "status": validation["status"],
        "provider_context_is_supplemental": True,
    }
    return retained, metadata

