"""Protected GitHub Actions controls for production data refreshes."""

from __future__ import annotations

from datetime import datetime, timezone
import hmac
import os
from typing import Any

import requests


REPOSITORY = os.getenv("REFRESH_GITHUB_REPOSITORY", "breckengalliher/fantasy-football-decision-lab")
WORKFLOWS = {
    "injuries": "daily-injury-refresh.yml",
    "context": "general-context-refresh.yml",
    "market": "market-data-refresh.yml",
    "projections": "weekly-production-refresh.yml",
    "all": "weekly-production-refresh.yml",
}
LABELS = {
    "injuries": "Injuries & practice",
    "context": "Live context & reporting",
    "projections": "Recalculate projections",
    "all": "Everything",
}


def configured() -> bool:
    return bool(os.getenv("ADMIN_REFRESH_PASSWORD") and os.getenv("GITHUB_ACTIONS_TOKEN"))


def authenticate(password: str) -> bool:
    expected = os.getenv("ADMIN_REFRESH_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(password.encode("utf-8"), expected.encode("utf-8"))


def _headers() -> dict[str, str]:
    token = os.getenv("GITHUB_ACTIONS_TOKEN", "")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def latest_run(workflow: str, timeout: int = 10) -> dict[str, Any] | None:
    response = requests.get(
        f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/{workflow}/runs",
        headers=_headers(), params={"event": "workflow_dispatch", "per_page": 1}, timeout=timeout,
    )
    response.raise_for_status()
    runs = response.json().get("workflow_runs", [])
    return runs[0] if runs else None


def trigger_refresh(kind: str, cooldown_minutes: int = 15, timeout: int = 10) -> dict[str, str]:
    if kind not in WORKFLOWS:
        raise ValueError("Unknown refresh type")
    if not configured():
        raise RuntimeError("Admin refresh secrets are not configured")
    workflow = WORKFLOWS[kind]
    previous = latest_run(workflow, timeout=timeout)
    if previous:
        if previous.get("status") in {"queued", "in_progress", "waiting", "pending"}:
            return {"state": "already_running", "message": f'{LABELS[kind]} refresh is already running.'}
        created = datetime.fromisoformat(str(previous["created_at"]).replace("Z", "+00:00"))
        age_minutes = (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds() / 60
        if age_minutes < cooldown_minutes:
            wait = max(1, int(cooldown_minutes - age_minutes + 0.999))
            return {"state": "cooldown", "message": f"Please wait about {wait} minute(s) before starting this refresh again."}
    response = requests.post(
        f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/{workflow}/dispatches",
        headers=_headers(), json={"ref": "main"}, timeout=timeout,
    )
    response.raise_for_status()
    return {"state": "requested", "message": f'{LABELS[kind]} refresh requested. GitHub will validate and publish it in the background.'}


def refresh_status(kind: str, timeout: int = 10) -> dict[str, str]:
    workflow = WORKFLOWS[kind]
    run = latest_run(workflow, timeout=timeout)
    if not run:
        return {"state": "none", "message": "No manual refresh has been recorded yet."}
    status = str(run.get("status", "unknown"))
    conclusion = str(run.get("conclusion") or "")
    display = {
        "queued": "Queued",
        "in_progress": "Fetching and validating",
        "completed": "Published" if conclusion == "success" else "Failed",
    }.get(status, status.replace("_", " ").title())
    return {"state": status, "message": f"Latest {LABELS[kind].lower()} refresh: {display}."}
