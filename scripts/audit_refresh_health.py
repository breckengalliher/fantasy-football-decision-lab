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
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    runs = get_with_retry(f"https://api.github.com/repos/{REPO}/actions/runs", params={"per_page": 100}, timeout=10).json()["workflow_runs"]
    base = f"https://raw.githubusercontent.com/{REPO}/main"
    report = {"checked_at": now.isoformat(), "read_only": True, "window_hours": 24, "jobs": []}
    for workflow in WORKFLOWS:
        text = get_with_retry(f"{base}/.github/workflows/{workflow}", timeout=10).text
        slots = expected_slots(text, now-timedelta(hours=24), now)
        relevant = [run for run in runs if run["path"].endswith(workflow)]
        row = job_health(relevant, slots[-1].isoformat() if slots else None, now)
        mature = matured_slot(slots, now)
        mature_health = job_health(relevant, mature, now)
        row["latest_execution_past_grace"] = mature
        row["overdue"] = row["overdue"] or mature_health["overdue"]
        row.update({"workflow": workflow, "expected_executions_24h": len(slots),
                    "observed_scheduled_starts_24h": sum(r.get("event") == "schedule" and r["created_at"] >= (now-timedelta(hours=24)).isoformat().replace("+00:00", "Z") for r in relevant),
                    "cadence_gap": len(slots) > sum(r.get("event") == "schedule" and r["created_at"] >= (now-timedelta(hours=24)).isoformat().replace("+00:00", "Z") for r in relevant),
                    "latest_run_url": relevant[0].get("html_url") if relevant else None})
        report["jobs"].append(row)
    report["published_metadata"] = get_with_retry(f"{base}/data/processed/live_refresh_metadata.json", timeout=10).json()
    report["scope_limitations"] = ["Cadence gaps are observed starts versus configured opportunities, not attribution of individual delayed triggers.",
                                  "Only the latest 100 repository runs are inspected; older failures may fall outside this window.",
                                  "GitHub completion does not prove source freshness or publication."]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(args.output), "jobs": report["jobs"]}, indent=2))


if __name__ == "__main__":
    main()
