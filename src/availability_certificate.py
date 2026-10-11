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
