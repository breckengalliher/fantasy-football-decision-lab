"""Append reviewed refresh evidence to the preserved full certification report."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "reports/release-certification-20261009"
artifact = json.loads((DEST / "artifact.json").read_text(encoding="utf-8"))
health = json.loads((DEST / "refresh-health.json").read_text(encoding="utf-8"))
tests = ET.parse(DEST / "refresh-tests.xml").getroot().find("testsuite")
title = "SDL expanded release certification October 9"
artifact["manifest"]["title"] = title
artifact["manifest"]["blocks"][0]["body"] = "# " + title
artifact["manifest"]["blocks"][1]["body"] = (
    "## Technical summary\n\n**NO GO for deployment.** Safe local refresh repairs are implemented, "
    "but all five release gates still need evidence or remediation. Scheduler gaps are confirmed; "
    "official injury/depth report times remain unavailable; the strict publication gate correctly "
    "rejects existing invalid raw forecasts. The preserved browser/container/hosting findings below "
    "remain applicable. The expanded refresh evidence follows those findings. No production data, "
    "real saved assignments, authentication settings, approved projection methodology, hosting cost, "
    "or deployment was changed."
)
source = {"id": "refresh-health", "label": "Read only refresh health audit",
          "path": "reports/release-certification-20261009/refresh-health.json",
          "query": {"description": "Configured Central-time schedule opportunities and actual scheduled starts in the same 24-hour window; latest 100 repository runs",
                    "metric_definitions": {"executions": "Count of configured trigger opportunities or observed schedule-event starts, not successful publications"}}}
artifact["manifest"]["sources"].append(source)
artifact["sources"].append(source)
artifact["manifest"]["sources"].extend([
    {"id": "refresh-tests", "label": "Expanded regression results", "path": "reports/release-certification-20261009/refresh-tests.xml"},
    {"id": "idle-process", "label": "Isolated local process measurement", "path": "reports/release-certification-20261009/idle-process-measurement.json"},
])
artifact["sources"] = artifact["manifest"]["sources"]


def section(identifier, heading, text, source_id=None):
    block = {"id": identifier, "type": "markdown", "body": "## " + heading + "\n\n" + text}
    if source_id:
        block["sourceId"] = source_id
    artifact["manifest"]["blocks"].append(block)


section("refresh-scheduler", "Scheduled starts do not meet configured cadence",
        "The audit ended October 9 at 10:59 AM Central and covers the preceding 24 hours. "
        "Injuries: 9 configured opportunities versus 3 scheduled starts; market: 48 versus 4; "
        "general context: 2 versus 2, but its latest expected morning window was overdue. Weekly "
        "production had no configured opportunity in this window. Equal daily counts do not prove "
        "each window ran on time. The latest injury run failed; a completed market job does not prove "
        "new props or publication. Counts are bounded by the latest 100 repository runs and cannot "
        "attribute individual delayed triggers. These cloud jobs already operate independently of "
        "Render traffic or service restarts. GitHub schedule delivery, not website traffic, remains "
        "an independent reliability concern. Local workflows serialize all publishers, retain queued "
        "runs and check out current main before refreshing. This addresses overlapping publication, "
        "not guaranteed trigger delivery.", "refresh-health")
rows = []
labels = {"weekly-production-refresh.yml": "Weekly", "daily-injury-refresh.yml": "Injuries",
          "general-context-refresh.yml": "Context", "market-data-refresh.yml": "Market"}
for job in health["jobs"]:
    for kind, key in (("Configured", "expected_executions_24h"), ("Observed", "observed_scheduled_starts_24h")):
        rows.append({"job": labels[job["workflow"]], "series": kind, "executions": job[key],
                     "checked_at": health["checked_at"], "window_hours": 24,
                     "last_result": job["last_result"], "overdue": job["overdue"],
                     "last_start": job["last_actual_start"], "last_success": job["last_successful_completion"],
                     "publication_verified": False})
connection = duckdb.connect()
connection.register("refresh_execution_counts", pd.DataFrame(rows))
query = "SELECT job, series, executions, checked_at, window_hours, last_result, overdue, last_start, last_success, publication_verified FROM refresh_execution_counts ORDER BY job, series"
rows = connection.execute(query).df().to_dict("records")
connection.close()
source["query"].update({"sql": query, "engine": "duckdb", "tables_used": ["refresh_execution_counts"],
                        "filters": ["24-hour window ending at audit checked_at", "Only latest 100 repository runs"]})
artifact["snapshot"]["datasets"]["scheduler"] = rows
artifact["manifest"]["charts"].append({
    "id": "scheduler", "title": "Configured and observed scheduled executions",
    "subtitle": "Preceding 24 hours ending October 9 at 10:59 AM Central; starts are not successful publications",
    "type": "bar", "dataset": "scheduler", "sourceId": "refresh-health", "source": source,
    "encodings": {"x": {"field": "job"}, "y": {"field": "executions"}, "color": {"field": "series"}},
    "options": {"grouping": "grouped", "showLegend": True},
})
artifact["manifest"]["blocks"].append({"id": "scheduler-chart", "type": "chart", "chartId": "scheduler"})
section("refresh-atomic", "Immutable snapshots prevent mixed versions in the new path",
        "Before: metadata and player files were mutable URLs with independent caches. After: the "
        "local publication protocol validates both scoring boards and weekly data, hashes assets, "
        "pins one complete Git revision, and pushes data plus its pointer in one remote ref update. "
        "Readers verify pinned hashes and use the same metadata version for board and weekly data. "
        "Invalid, incomplete or hash-mismatched candidates do not replace the last valid pointer. "
        "The current raw boards contain a missing forecast and previously documented inverted "
        "intervals; strict validation correctly blocks them. No missing values were invented and "
        "no intervals were silently clamped. The legacy path is explicitly unverified until an "
        "approved versioned publication exists. Actual successful publication timestamps and "
        "source-version attribution are not yet complete: pointer preparation time is deliberately "
        "not labeled as successful remote publication. Auxiliary context files and restart recovery "
        "still need complete immutable-bundle integration.")
section("refresh-freshness", "Downloaded reports no longer qualify a lineup as ready",
        "Before: recent retrieval could be interpreted as current availability. After: READY needs "
        "explicit verified injury and depth freshness as well as existing age checks. Retrieved "
        "time and underlying report freshness have separate labels; unknown official report age "
        "produces VERIFY DATA. Provider response timestamps are never fabricated. The provider "
        "checks above prove access, not official report currency. A timestamp-capable official "
        "report/inactive source and kickoff-aware reporting thresholds remain required for certification.")
section("refresh-browser", "Idle updates and draft protection passed an isolated browser test",
        "Before: idle pages needed a user interaction. After: a 60-second fragment checks a small "
        "pointer with a 30-second process cache; unchanged versions do not reload datasets or rerun "
        "the full app. A changed version is preloaded and checked before a redraw. The actual "
        "production fragment was exercised with a local version fixture: v1 changed to v2 without "
        "reloading; v3 was deferred while an unsaved league-name draft was present; saving and "
        "closing the edit resumed v3. The draft, selected disposable team and session indicator "
        "were preserved. At 390 by 844, the harness document width and scroll width were both "
        "390. This is not a real-account end-to-end security test. Server-known settings, management "
        "and player selection defer updates; unsent search text and other forms require additional "
        "full-app coverage. Reconnection and restart during a live refresh are not yet certified.")
section("refresh-recovery", "Last validated public data survives a failed candidate locally",
        "A bounded process-level recovery store retains references to at most two public snapshots "
        "for the supported scoring formats. Failed downloads or verification retain the previous "
        "complete data and original timestamps, mark the outage visibly, and disable injury/depth "
        "freshness reassurance. A four-point snapshot cannot substitute for six-point scoring. "
        "No private user information is stored. This is process recovery, not durable restart "
        "recovery: a restarted service still needs its immutable published assets. Tests cover "
        "bounded retention and no promotion of legacy or offline metadata.")
section("refresh-tests", "The original baseline is preserved with additional refresh regressions",
        f"The final suite passed {tests.attrib['tests']} tests with zero failures or errors in "
        f"{float(tests.attrib['time']):.2f} seconds. The preserved baseline was 230 tests in 7.88 seconds; the larger suite is "
        "not a like-for-like application speed benchmark. Two existing Pandas warnings and one "
        "environmental pytest-cache warning occurred in an earlier run; the final run disabled that cache plugin. Coverage includes repeated provider merges, "
        "unknown source age, stale successful downloads, unchanged pointers, invalid snapshots, "
        "hash failures, scoring identity mismatch, bounded timeout retries, nonretryable denial, "
        "missed-run detection, queued workflow protocol, draft deferral and last-good recovery. "
        "The complete 17-scenario integration matrix is not yet passed: real overlapping cloud "
        "runs, process restart mid-publication, browser disconnection, cache-expiry concurrency "
        "and independently authenticated edits remain open.", "refresh-tests")
section("refresh-performance", "Local idle overhead is small in one isolated sample",
        "Over 45.04 seconds, the isolated one-browser QA server consumed 0.5469 CPU seconds, "
        "or 1.21 percent of one logical core. Working set changed from 131.16 to 131.03 MB. "
        "These built-in Windows process counters do not measure incremental polling memory, "
        "peak memory, the full Command Center, or Render. There is no before polling baseline. "
        "Configured steady-state polling is one small pointer check per browser minute; the "
        "shared cache suppresses eligible duplicate requests for 30 seconds. Actual concurrent "
        "HTTP counts, publication latency and hosted UI percentiles remain unmeasured. No NFL "
        "provider calls occur in the idle pointer checker. Render Starter is still a candidate, "
        "not a verified ten-account capacity guarantee.", "idle-process")
section("expanded-gates", "All five certification gates remain on hold",
        "1. **Official injury/depth: BLOCKED.** Source timestamps and official inactive evidence remain unverified; conservative warnings are implemented.\n"
        "2. **Persistence/security: PARTIAL.** Prior restoration smoke and local regressions pass. A complete edited roster close/reopen journey plus two independent account authorization tests remain required.\n"
        "3. **Production container: UNVERIFIED.** Packaging regression passes; Docker and Python 3.12 container execution are not available locally.\n"
        "4. **Hosted performance: UNVERIFIED.** Ten anonymous browser sessions rendered; exact user latency and CPU/RAM concurrency measurements remain outstanding.\n"
        "5. **Refresh delivery: PARTIAL AND BLOCKED.** Idle/draft tests and atomic protocol tests pass locally. Cadence gaps, invalid raw forecasts, full-app form coverage, complete publication timestamps and restart integration remain unresolved.")
section("expanded-next", "Resolve the release blockers before requesting deployment",
        "1. Recover valid missing forecast inputs and settle an explicit publication-quarantine or interval policy without silently changing the approved model.\n"
        "2. Add a separately approved independent scheduler heartbeat/fallback; a no-cost existing computer scheduler is possible but cannot guarantee availability when the computer sleeps. A Render-hosted watchdog would require tested lifecycle, secret and resource controls. No fallback has been enabled in production.\n"
        "3. Obtain provider-supported official update/report times and document practice, inactive and kickoff expectations.\n"
        "4. Complete durable immutable-bundle recovery and all 17 failure/recovery integration scenarios.\n"
        "5. Run the production container, authenticated browser/mobile journey and measured hosted concurrency.\n"
        "6. Ask for explicit deployment approval only after these gates pass or a specific safe fallback is approved.")
section("expanded-implementation", "Local files and functions changed for refresh reliability",
        "- dashboard/providers/sportsdataio.py enrich_board: remove prior provider-owned merge fields before repeated refreshes; validate unique team context.\n"
        "- dashboard/providers/http_retry.py get_with_retry and injuries.py retrieval: bounded read-only retries and explicit network timeouts.\n"
        "- src/refresh_live_context.py and src/refresh_weekly_snapshot.py: retain separate retrieval and source-verification metadata.\n"
        "- src/publication.py validate_snapshot/build_manifest/write_manifest and scripts/prepare_publication.py: strict validation, asset hashes and immutable revision pointer.\n"
        "- All four refresh workflows: serialize publishers, queue runs, prepare pointer before a single push. Changes remain local.\n"
        "- dashboard/publication_client.py read_metadata/verified_payload: pinned metadata and hash-checked assets.\n"
        "- dashboard/live_updates.py watch_publication/update_decision/editing_roster: lightweight idle checks and conservative edit deferral.\n"
        "- dashboard/snapshot_recovery.py SnapshotRecovery.load: bounded public-only last-good recovery.\n"
        "- dashboard/app.py get_snapshot_metadata/get_published_snapshot/_prepare_idle_update: coherent version cache keys, verified preload and recovered timestamps.\n"
        "- dashboard/lineup_rules.py critical_data_fresh, trust_layer.py and app status copy: no READY from retrieval time alone.\n"
        "- dashboard/refresh_health.py and scripts/audit_refresh_health.py: read-only cadence, failures and overdue reporting.\n"
        "- dashboard/admin_refresh.py: market action label and completion wording that does not falsely promise publication.\n"
        "- New publication, workflow, recovery, retry, health and idle-update tests plus existing merge/freshness regressions.\n"
        "Shared data caches contain public datasets only. Timer pointer cache is bounded to one entry; main snapshot resource cache is bounded to four entries; recovery retains two public references. No model retraining or prediction-weight change was introduced.")
section("expanded-questions", "Decisions needed to finish certification",
        "Can the existing providers supply official report timestamps and inactive confirmations? "
        "Should invalid backup forecasts be explicitly quarantined from publication while preserving "
        "their raw audit records, or should publication wait for corrected source inputs? Which "
        "independent scheduling mechanism is approved for production? These are release decisions, "
        "not permissions assumed by the local prototype.")
artifact["snapshot"]["generatedAt"] = health["checked_at"]
artifact["package_info"] = {"notes": "Technical audience; existing checkpoint sections preserved. Expanded evidence covers all five release gates. Grouped bar uses configured vs observed start counts, not freshness or publication success. No claims of production certification."}
(DEST / "expanded-artifact.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
print(DEST / "expanded-artifact.json")
