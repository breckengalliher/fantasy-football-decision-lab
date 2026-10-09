"""Read-only operational audit. No provider refresh or GitHub mutations."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard.providers.http_retry import get_with_retry
from dashboard.refresh_health import expected_slots, job_health, matured_slot

REPO = "breckengalliher/fantasy-football-decision-lab"
WORKFLOWS = ["weekly-production-refresh.yml", "daily-injury-refresh.yml",
             "general-context-refresh.yml", "market-data-refresh.yml"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports/release-certification-20261009/refresh-health.json")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if not 1 <= args.days <= 14:
        raise ValueError("Bound audit history to 1–14 days")
    window_start = now - timedelta(days=args.days)
    base = f"https://raw.githubusercontent.com/{REPO}/main"
    report = {"checked_at": now.isoformat(), "read_only": True, "window_hours": args.days * 24, "jobs": []}
    for workflow in WORKFLOWS:
        text = get_with_retry(f"{base}/.github/workflows/{workflow}", timeout=10).text
        changes = get_with_retry(f"https://api.github.com/repos/{REPO}/commits",
                                params={"path": f".github/workflows/{workflow}", "per_page": 100}, timeout=10).json()
        versions = sorted(changes, key=lambda c: c["commit"]["committer"]["date"])
        slots, configuration_intervals = [], []
        for index, change in enumerate(versions):
            beginning = datetime.fromisoformat(change["commit"]["committer"]["date"].replace("Z", "+00:00"))
            ending = datetime.fromisoformat(versions[index+1]["commit"]["committer"]["date"].replace("Z", "+00:00")) if index+1 < len(versions) else now
            if ending <= window_start:
                continue
            start = max(beginning, window_start)
            historical = get_with_retry(f"https://raw.githubusercontent.com/{REPO}/{change['sha']}/.github/workflows/{workflow}", timeout=10).text
            observed_slots = [s for s in expected_slots(historical, start, ending) if start <= s < ending]
            slots.extend(observed_slots)
            configuration_intervals.append({"revision": change["sha"], "start": start.isoformat(), "end": ending.isoformat(), "expected": len(observed_slots)})
        slots = sorted(set(slots))
        relevant = []
        complete = False
        for page in range(1, 11):
            batch = get_with_retry(f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow}/runs",
                params={"per_page": 100, "page": page,
                        "created": ">=" + window_start.strftime("%Y-%m-%dT%H:%M:%SZ")}, timeout=10).json()["workflow_runs"]
            relevant.extend(batch)
            if len(batch) < 100:
                complete = True
                break
        row = job_health(relevant, slots[-1].isoformat() if slots else None, now)
        mature = matured_slot(slots, now)
        mature_health = job_health(relevant, mature, now)
        row["latest_execution_past_grace"] = mature
        row["overdue"] = row["overdue"] or mature_health["overdue"]
        scheduled = [r for r in relevant if r.get("event") == "schedule"]
        row.update({"workflow": workflow, "expected_executions": len(slots),
                    "observed_scheduled_starts": len(scheduled),
                    "history_complete": complete,
                    "cadence_gap": len(slots) > len(scheduled) if complete else None,
                    "failed_runs": sum(r.get("conclusion") == "failure" for r in relevant),
                    "cancelled_runs": sum(r.get("conclusion") == "cancelled" for r in relevant),
                    "unfinished_runs": sum(r.get("status") != "completed" for r in relevant),
                    "latest_run_url": relevant[0].get("html_url") if relevant else None})
        row["runs"] = [{key: run.get(key) for key in ("id", "event", "created_at", "run_started_at", "updated_at", "status", "conclusion", "head_sha", "run_attempt", "html_url")} for run in relevant]
        row["schedule_configuration_intervals"] = configuration_intervals
        report["jobs"].append(row)
    report["published_metadata"] = get_with_retry(f"{base}/data/processed/live_refresh_metadata.json", timeout=10).json()
    report["scope_limitations"] = ["Cadence gaps are observed starts versus configured opportunities, not attribution of individual delayed triggers.",
                                  "Workflow-specific history is paginated up to 1,000 runs per workflow; incomplete history is explicitly flagged.",
                                  "Expected opportunities use committed historical configurations and exclude time before workflow creation.",
                                  "GitHub completion does not prove source freshness or publication."]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(args.output), "jobs": report["jobs"]}, indent=2))


if __name__ == "__main__":
    main()
