"""Pure operational health rules; no network work during public interactions."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re


def timestamp(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def matured_slot(slots, now, grace_minutes=90):
    """A newly due slot must not hide an older unfulfilled execution."""
    matured = [slot for slot in slots if now - slot > timedelta(minutes=grace_minutes)]
    return max(matured).isoformat() if matured else None


def job_health(runs, expected_at, now, *, grace_minutes=90):
    ordered = sorted(runs, key=lambda r: r["created_at"], reverse=True)
    failures = 0
    for run in ordered:
        if run.get("status") != "completed":
            continue
        if run.get("conclusion") == "failure":
            failures += 1
        else:
            break
    successes = [r for r in ordered if r.get("conclusion") == "success"]
    failed = [r for r in ordered if r.get("conclusion") == "failure"]
    scheduled = [r for r in ordered if r.get("event") == "schedule"]
    last = ordered[0] if ordered else {}
    actual = timestamp(scheduled[0]["created_at"]) if scheduled else None
    due = timestamp(expected_at)
    overdue = bool(due and now - due > timedelta(minutes=grace_minutes) and (actual is None or actual < due))
    start, finish = timestamp(last.get("run_started_at")), timestamp(last.get("updated_at"))
    return {
        "expected_execution": due.isoformat() if due else None,
        "last_scheduled_execution": scheduled[0]["created_at"] if scheduled else None,
        "last_actual_start": last.get("run_started_at"),
        "last_successful_completion": successes[0].get("updated_at") if successes else None,
        "last_failure": failed[0].get("updated_at") if failed else None,
        "duration_seconds": max(0, (finish-start).total_seconds()) if finish and start else None,
        "last_result": last.get("conclusion") or last.get("status") or "unverified",
        "consecutive_failures": failures, "overdue": overdue,
        "publication_verified": False,  # Completion alone cannot prove publication.
    }


def cron_matches(expression, moment):
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Expected five-field cron")
    values = [moment.minute, moment.hour, moment.day, moment.month, (moment.weekday() + 1) % 7]
    def matches(field, value, lower, upper):
        for item in field.split(","):
            interval, _, step = item.partition("/")
            stride = int(step or 1)
            if stride <= 0:
                raise ValueError("Invalid cron step")
            if interval == "*":
                start, end = lower, upper
            elif "-" in interval:
                start, end = map(int, interval.split("-"))
            else:
                start = end = int(interval)
            if start <= value <= end and (value-start) % stride == 0:
                return True
        return False
    return all(matches(field, value, lower, upper) for field, value, (lower, upper) in
               zip(fields, values, [(0,59), (0,23), (1,31), (1,12), (0,6)]))


def expected_slots(workflow_text, start, end):
    # SDL uses explicit five-field crons and a timezone for every schedule.
    schedules = re.findall(r'- cron:\s*"([^"]+)"\s*\n\s*timezone:\s*"([^"]+)"', workflow_text)
    if not schedules:
        raise ValueError("Schedule unavailable or unsupported; do not infer healthy")
    cursor = start.astimezone(timezone.utc).replace(second=0, microsecond=0)
    slots = []
    while cursor <= end:
        if any(cron_matches(cron, cursor.astimezone(ZoneInfo(zone))) for cron, zone in schedules):
            slots.append(cursor)
        cursor += timedelta(minutes=1)
    return slots
