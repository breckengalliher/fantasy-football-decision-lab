"""Controlled ten-session Streamlit concurrency smoke test.

This runs locally with Streamlit's AppTest. It is deliberately not a network
load test and never targets production.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def rss_bytes() -> int:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-Process -Id {os.getpid()}).WorkingSet64",
    ]
    return int(subprocess.check_output(command, text=True).strip())


def run_session(timeout: float) -> dict[str, object]:
    started = time.perf_counter()
    try:
        app = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=timeout)
        app.query_params["view"] = "home"
        app.run(timeout=timeout)
        errors = [str(item.value) for item in app.exception]
        return {"duration_ms": round((time.perf_counter() - started) * 1000, 2), "errors": errors}
    except Exception as error:  # surfaced in the JSON rather than hidden by a worker
        return {"duration_ms": round((time.perf_counter() - started) * 1000, 2), "errors": [repr(error)]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    before = rss_bytes()
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.sessions) as executor:
        results = list(executor.map(lambda _: run_session(args.timeout), range(args.sessions)))
    wall_ms = round((time.perf_counter() - started) * 1000, 2)
    durations = [float(result["duration_ms"]) for result in results]
    ordered = sorted(durations)
    report = {
        "environment": "local Streamlit AppTest threads; not an HTTP production load test",
        "sessions": args.sessions,
        "wall_ms": wall_ms,
        "session_p50_ms": round(statistics.median(durations), 2),
        "session_p95_ms": round(ordered[min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))], 2),
        "rss_before_mb": round(before / 1_048_576, 2),
        "rss_after_mb": round(rss_bytes() / 1_048_576, 2),
        "successful_sessions": sum(not result["errors"] for result in results),
        "results": results,
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
