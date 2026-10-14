"""Publication gate for the reviewed, real-source availability certificate.

This validates claims and cross-file consistency. It cannot independently prove
that a human/source extractor read a page correctly; raw receipts remain part
of release review. A structural snapshot pass is not a football certification.
"""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from dashboard.availability_evidence import resolve_availability, timestamp, report_time, certificate_digest


def validate_certificate(certificate, boards, metadata, now=None):
    now = now or datetime.now(timezone.utc)
    if isinstance(certificate, dict) and certificate.get("schema_version") == 2:
        return validate_restricted_certificate(certificate, boards, metadata, now)
    if not isinstance(certificate, dict) or certificate.get("schema_version") != 1:
        raise ValueError("Availability certificate missing or unsupported")
    if certificate.get("season") != metadata.get("season") or certificate.get("week") != metadata.get("next_week"):
        raise ValueError("Availability certificate season/week mismatch")
    if certificate.get("synthetic") is not False:
        raise ValueError("Synthetic availability evidence cannot be published")
    sources = certificate.get("sources", {})
    if not sources:
        raise ValueError("Availability source receipts missing")
    for source in sources.values():
        url = urlsplit(str(source.get("url", "")))
        retrieved, report = timestamp(source.get("retrieved_at")), report_time(source)
        if (url.scheme != "https" or not url.hostname or source.get("authority") != "official"
                or not re.fullmatch(r"[a-f0-9]{64}", str(source.get("sha256", "")))
                or source.get("timestamp_basis") not in {"published", "effective"}
                or not retrieved or not report or not report <= retrieved <= now):
            raise ValueError("Availability source receipt or report timestamp invalid")
    records = certificate.get("players", [])
    ids = [r.get("player_id") for r in records]
    if not ids or None in ids or len(ids) != len(set(ids)):
        raise ValueError("Availability certificate identities missing or duplicated")
    expiry = []
    for board in boards:
        if "is_roster_relevant" not in board or "injury_status_live" not in board:
            raise ValueError("Availability board schema missing")
        eligible = board.loc[board.is_roster_relevant.eq(True)].set_index("player_id")
        if set(eligible.index) != set(ids):
            raise ValueError("Availability certificate does not cover eligible players exactly")
        for record in records:
            row = eligible.loc[record["player_id"]]
            if any(record.get(k) != row[k] for k in ("player", "team", "position")):
                raise ValueError("Availability certificate player/team mismatch")
            if record.get("identity_verified") is not True or record.get("conflicts") != []:
                raise ValueError("Unresolved availability identity or conflict")
            game = record.get("game", {})
            if game.get("mapping_verified") is not True or game.get("source_id") not in sources:
                raise ValueError("Unverified game mapping")
            if not game.get("bye") and (not game.get("game_id") or not timestamp(game.get("kickoff_at"))):
                raise ValueError("Missing game identity or kickoff")
            if game.get("bye") is True and game.get("kickoff_at") is not None:
                raise ValueError("Bye conflicts with scheduled kickoff")
            if game.get("bye") is not bool(row.get("bye_week", False)):
                raise ValueError("Board bye differs from verified game")
            if not game.get("bye") and (not game.get("opponent") or game["opponent"] != row.get("next_opponent")):
                raise ValueError("Board opponent differs from verified game")
            if str(game.get("status", "scheduled")).casefold() != str(row.get("game_status_live", "scheduled")).casefold():
                raise ValueError("Board game state differs from verified game")
            from dashboard.availability import kickoff_utc
            if not game.get("bye") and kickoff_utc(row) != timestamp(game["kickoff_at"]):
                raise ValueError("Board kickoff differs from verified game")
            injury = record.get("injury_coverage", {})
            depth = record.get("depth", {})
            for coverage in (injury, depth):
                until = timestamp(coverage.get("valid_until"))
                if coverage.get("source_id") not in sources or not until or until <= now:
                    raise ValueError("Missing or expired injury/depth coverage")
                expiry.append(until)
            if injury.get("complete") is not True:
                raise ValueError("Incomplete injury coverage")
            if depth.get("classification") not in {"official_confirmed", "club_unofficial", "not_used"}:
                raise ValueError("Unclassified depth evidence")
            if depth.get("confirmed_starter") is True and depth["classification"] != "official_confirmed":
                raise ValueError("Projected depth cannot confirm a starter")
            inactive = record.get("inactives", {})
            due = timestamp(inactive.get("due_at"))
            if not game.get("bye"):
                from datetime import timedelta
                if due != timestamp(game["kickoff_at"]) - timedelta(minutes=90):
                    raise ValueError("Inactive publication due time mismatch")
                if inactive.get("state") == "not_yet_due" and now < due:
                    expiry.append(due)
                elif inactive.get("state") != "published" or inactive.get("source_id") not in sources:
                    raise ValueError("Due inactive list missing")
            events = record.get("events", [])
            for event in events:
                source = sources.get(event.get("source_id"), {})
                if (not source or event.get("authority") != source.get("authority")
                        or event.get("timestamp_basis") != source.get("timestamp_basis")
                        or report_time(event) != report_time(source)
                        or event.get("effective_date") != source.get("effective_date")
                        or event.get("report_timezone") != source.get("report_timezone")):
                    raise ValueError("Availability event is not bound to its source report")
                until = timestamp(event.get("valid_until"))
                if until and until > now:
                    expiry.append(until)
            resolved = resolve_availability(events, player_id=record["player_id"], team=record["team"],
                game_id=game.get("game_id"), kickoff_at=game.get("kickoff_at"), now=now,
                game_status=game.get("status", "scheduled"), bye=game.get("bye", False))
            if (resolved["roster_eligibility"] == "unknown" or resolved["availability"] == "Unknown"
                    or any(x not in {"unavailable", "game bye", "game started", "game final", "game postponed"}
                           for x in resolved["restrictions"])):
                raise ValueError("Unverified or conflicting player availability")
            if row.injury_status_live != resolved["availability"]:
                raise ValueError("Board availability differs from source precedence")
    return {"status": "verified", "sha256": certificate_digest(certificate),
            "player_count": len(ids), "valid_until": min(expiry).isoformat()}


def validate_restricted_certificate(certificate, boards, metadata, now):
    """Publish explicit uncertainty without certifying unsupported recommendations.

    This policy is deliberately global: every availability recommendation stays
    blocked. It does not convert an undated observation into a published claim,
    or waive the separate launch requirement for verified availability.
    """
    if (certificate.get("policy") != "all_availability_actions_blocked"
            or certificate.get("synthetic") is not False
            or metadata.get("injury_freshness_verified") is not False
            or metadata.get("depth_freshness_verified") is not False):
        raise ValueError("Restricted publication must block all availability actions")
    if certificate.get("season") != metadata.get("season") or certificate.get("week") != metadata.get("next_week"):
        raise ValueError("Availability certificate season/week mismatch")
    sources = certificate.get("sources", {})
    if not sources:
        raise ValueError("Availability source receipts missing")
    for source in sources.values():
        url = urlsplit(str(source.get("url", "")))
        retrieved = timestamp(source.get("retrieved_at"))
        if (url.scheme != "https" or not url.hostname or source.get("authority") != "official"
                or not re.fullmatch(r"[a-f0-9]{64}", str(source.get("sha256", "")))
                or not retrieved or retrieved > now):
            raise ValueError("Invalid restricted source receipt")
        # Undated raw evidence is allowed for audit only, never as a dated event.
        if source.get("timestamp_basis") in {"published", "effective"}:
            at = report_time(source)
            if not at or at > retrieved:
                raise ValueError("Invalid claimed source report time")
        elif source.get("timestamp_basis") != "undated_observation":
            raise ValueError("Unclassified source report time")
    records = certificate.get("players", [])
    ids = [r.get("player_id") for r in records]
    if not ids or None in ids or len(ids) != len(set(ids)):
        raise ValueError("Availability certificate identities missing or duplicated")
    valid_classes = {"VERIFIED", "PENDING OFFICIAL REPORT", "UNKNOWN", "CONFLICTING", "OUTSIDE ACTIONABLE SCOPE"}
    for board in boards:
        required = {"is_roster_relevant", "injury_status_live", "game_status_live", "bye_week", "next_opponent"}
        if not required <= set(board):
            raise ValueError("Restricted availability board schema missing")
        eligible = board.loc[board.is_roster_relevant.eq(True)].set_index("player_id")
        if set(eligible.index) != set(ids):
            raise ValueError("Availability certificate does not cover eligible players exactly")
        for record in records:
            row = eligible.loc[record["player_id"]]
            if record.get("identity_verified") is not True or any(record.get(k) != row[k] for k in ("player", "team", "position")):
                raise ValueError("Unverified identity in restricted publication")
            if record.get("classification") not in valid_classes or record.get("recommendation_allowed") is not False:
                raise ValueError("Restricted player recommendation is not blocked")
            game = record.get("game", {})
            if game.get("mapping_verified") is not True or game.get("source_id") not in sources:
                raise ValueError("Unverified game mapping")
            if game.get("bye") is not bool(row.get("bye_week", False)):
                raise ValueError("Board bye differs from verified game")
            if game.get("bye"):
                if game.get("kickoff_at") is not None:
                    raise ValueError("Bye conflicts with scheduled kickoff")
            else:
                from datetime import timedelta
                from dashboard.availability import kickoff_utc
                kickoff = timestamp(game.get("kickoff_at"))
                if (not kickoff or not game.get("game_id") or kickoff_utc(row) != kickoff
                        or not game.get("opponent") or game.get("opponent") != row.next_opponent):
                    raise ValueError("Restricted game mapping differs from board")
                inactive = record.get("inactives", {})
                due = timestamp(inactive.get("due_at"))
                if due != kickoff - timedelta(minutes=90):
                    raise ValueError("Inactive publication due time mismatch")
                if inactive.get("state") == "not_yet_due" and now >= due:
                    raise ValueError("Future inactive claim has expired")
                if inactive.get("state") not in {"not_yet_due", "published", "due_missing", "incomplete", "conflicting"}:
                    raise ValueError("Unclassified inactive coverage")
                if inactive.get("state") == "published" and inactive.get("source_id") not in sources:
                    raise ValueError("Published inactive source missing")
            if str(game.get("status", "scheduled")).casefold() != str(row.game_status_live).casefold():
                raise ValueError("Board game state differs from verified game")
            depth = record.get("depth", {})
            if (depth.get("classification") not in {"official_confirmed", "club_unofficial", "unknown", "not_used"}
                    or depth.get("confirmed_starter") is not False):
                raise ValueError("Restricted snapshot cannot claim a confirmed starting role")
            events = record.get("events", [])
            for event in events:
                source = sources.get(event.get("source_id"), {})
                at = report_time(event)
                if (source.get("timestamp_basis") not in {"published", "effective"}
                        or event.get("authority") != "official" or event.get("timestamp_basis") != source.get("timestamp_basis")
                        or not at or at != report_time(source)
                        or event.get("effective_date") != source.get("effective_date")
                        or event.get("report_timezone") != source.get("report_timezone")
                        or not timestamp(event.get("valid_until"))):
                    raise ValueError("Restricted event lacks a bound source timestamp")
            result = resolve_availability(events, player_id=record["player_id"], team=record["team"],
                game_id=game.get("game_id"), kickoff_at=game.get("kickoff_at"), now=now,
                game_status=game.get("status", "scheduled"), bye=game.get("bye", False))
            if row.injury_status_live != result["availability"]:
                raise ValueError("Restricted board differs from source precedence")
            if record.get("classification") == "VERIFIED" and (result["availability"] == "Unknown" or record.get("conflicts")):
                raise ValueError("Unknown/conflicting player cannot be labelled verified")
    return {"status": "restricted", "sha256": certificate_digest(certificate),
            "player_count": len(ids), "all_availability_actions_blocked": True,
            "unknown_count": sum(r["classification"] == "UNKNOWN" for r in records)}
