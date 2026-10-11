"""Resolve dated football evidence without conflating health, roster and game state.

Source extraction is a separate, reviewed step. Retrieval time is never an
event's effective time. Unknown evidence is a blocking result, not Available.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROSTER_RESERVE = {"ir", "pup", "nfi", "reserve", "suspended", "exempt"}
VALUES = {
    "roster": ROSTER_RESERVE | {"active", "activated"},
    "injury": {"out", "doubtful", "questionable", "available"},
    "gameday": {"inactive", "active"},
}


def timestamp(value):
    """Reject absent/naive dates rather than silently assigning a timezone."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def report_time(record):
    """Comparison bound for date-only reports; do not fabricate a clock time.

    A dated transaction is effective sometime on that civil day. Its exclusive
    end bound is safe to order against later days; same-day conflicts remain
    unresolved. The original date/precision is retained in the certificate.
    """
    exact = timestamp(record.get("effective_at", record.get("report_at")))
    if exact:
        return exact
    try:
        day = date.fromisoformat(record["effective_date"])
        zone = ZoneInfo(record["report_timezone"])
        return datetime.combine(day + timedelta(days=1), datetime.min.time(), zone).astimezone(timezone.utc)
    except (KeyError, ValueError, TypeError, ZoneInfoNotFoundError):
        return None


def report_start(record):
    if record.get("effective_date"):
        try:
            return datetime.combine(date.fromisoformat(record["effective_date"]), datetime.min.time(),
                                    ZoneInfo(record["report_timezone"])).astimezone(timezone.utc)
        except (KeyError, ValueError, TypeError, ZoneInfoNotFoundError):
            return None
    return report_time(record)


def is_later(left, right):
    return (report_start(left) > report_time(right)
            or (report_start(left) == report_time(right) and bool(right.get("effective_date"))))


def resolve_availability(events, *, player_id, team, game_id, kickoff_at, now,
                         game_status="scheduled", bye=False):
    now = now.astimezone(timezone.utc)
    kickoff = timestamp(kickoff_at)
    state = str(game_status).casefold()
    game = ("bye" if bye else "postponed" if state in {"postponed", "rescheduled", "cancelled", "canceled"}
            else "final" if state in {"final", "closed"}
            else "started" if state in {"in progress", "started"} or (kickoff and kickoff <= now)
            else "scheduled" if kickoff else "unknown")
    issues, usable = [], []
    for event in events:
        domain, status = event.get("domain"), event.get("status")
        at, until = report_time(event), timestamp(event.get("valid_until"))
        reason = None
        if event.get("player_id") != player_id or event.get("team") != team:
            reason = "identity mismatch"
        elif domain not in VALUES or status not in VALUES[domain]:
            reason = "unsupported designation"
        elif domain != "roster" and event.get("game_id") != game_id:
            continue  # A historical game's inactive list cannot govern this game.
        elif event.get("authority") != "official" or event.get("timestamp_basis") not in {"published", "effective"}:
            reason = "unverified authority or timestamp basis"
        elif not at or not until or not at <= now < until:
            reason = "missing, future or stale report time"
        if reason == "missing, future or stale report time" and at and until and until <= now:
            # A dated later report may supersede expired history. Reserve history
            # requires an explicit activation, not an active-roster observation.
            newer = [e for e in events if e.get("domain") == domain
                     and e.get("player_id") == player_id and e.get("team") == team
                     and e.get("authority") == "official"
                     and e.get("timestamp_basis") in {"published", "effective"}
                     and report_time(e) and timestamp(e.get("valid_until"))
                     and is_later(e, event) and report_time(e) <= now < timestamp(e["valid_until"])
                     and (domain == "roster" or e.get("game_id") == game_id)
                     and (domain != "roster" or status not in ROSTER_RESERVE or e.get("status") == "activated")]
            if newer:
                continue
        if reason:
            issues.append(reason)
        else:
            usable.append(event)

    def latest(domain):
        rows = [e for e in usable if e["domain"] == domain]
        if not rows:
            return None
        winner = max(rows, key=report_time)
        rows = [e for e in rows if not is_later(winner, e)]
        if len({e["status"] for e in rows}) != 1:
            issues.append(f"conflicting {domain} designations at the same effective time")
            return None
        return sorted(rows, key=lambda e: e.get("source_id", ""))[0]

    roster, injury, gameday = latest("roster"), latest("injury"), latest("gameday")
    # A generic active-roster listing cannot silently clear a reserve transaction.
    reserves = [e for e in usable if e["domain"] == "roster" and e["status"] in ROSTER_RESERVE]
    if reserves:
        reserve = max(reserves, key=report_time)
        activations = [e for e in usable if e["domain"] == "roster" and e["status"] == "activated"
                       and is_later(e, reserve)]
        if not activations:
            roster = reserve
    roster_state = ("active" if roster and roster["status"] in {"active", "activated"}
                    else roster["status"] if roster else "unknown")
    status = "Unknown"
    # A current game's inactive designation outranks roster membership/activation.
    if gameday and gameday["status"] == "inactive":
        status = "Inactive"
    elif roster_state in ROSTER_RESERVE:
        status = {"ir": "IR", "pup": "PUP", "nfi": "NFI"}.get(roster_state, roster_state.title())
    elif injury:
        status = injury["status"].title()
    # An explicit later official game-active report can supersede an earlier OUT.
    if (gameday and gameday["status"] == "active" and roster_state == "active"
            and (not injury or is_later(gameday, injury))):
        status = "Available"
    if roster_state == "unknown":
        issues.append("roster eligibility unverified")
    if status == "Unknown":
        issues.append("injury/game availability unverified")
    # Invalid/conflicting evidence never authorizes a positive recommendation.
    if issues and status in {"Available", "Questionable", "Doubtful"}:
        status = "Unknown"
    restrictions = list(dict.fromkeys(issues))
    if game != "scheduled":
        restrictions.append(f"game {game}")
    if status not in {"Available", "Questionable", "Doubtful"}:
        restrictions.append("unavailable" if status != "Unknown" else "verify availability")
    return {"availability": status, "roster_eligibility": roster_state,
            "game_state": game, "recommendation_allowed": not restrictions,
            "restrictions": list(dict.fromkeys(restrictions)),
            "source_ids": sorted({e.get("source_id", "") for e in usable})}
