"""Real HTTP and filesystem fault injection against disposable QA copies."""
import json
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.publication import FILES, validate_snapshot, write_manifest
from dashboard.publication_client import verified_payload
from dashboard.snapshot_recovery import SnapshotRecovery


def main():
    source = ROOT / "reports/production-certification-20261009/isolated-staging-190d/data/processed"
    original = json.loads((source / "publication_manifest.json").read_text())
    results = []
    with tempfile.TemporaryDirectory(prefix="sdl-qa-faults-", dir=ROOT / "reports") as temporary:
        destination = Path(temporary)
        for name in (*FILES, "publication_manifest.json"):
            shutil.copy2(source / name, destination / name)
        pointer_bytes = (destination / "publication_manifest.json").read_bytes()
        def exercise(label, mutation):
            try:
                mutation()
                write_manifest(destination, "b" * 40)
                raise AssertionError("Invalid publication was accepted")
            except (ValueError, FileNotFoundError, OSError, json.JSONDecodeError) as error:
                assert (destination / "publication_manifest.json").read_bytes() == pointer_bytes
                results.append({"case": label, "result": "rejected", "error_type": type(error).__name__, "last_good_pointer_unchanged": True})
            for name in FILES:
                shutil.copy2(source / name, destination / name)
        exercise("invalid-response-schema", lambda: (destination / FILES[-1]).write_text('{"unexpected":true}'))
        exercise("incomplete-data", lambda: (destination / FILES[2]).unlink())
        def bad_forecast():
            board = pd.read_parquet(destination / FILES[0])
            board.loc[0, "median_ppr"] = -100
            board.to_parquet(destination / FILES[0], index=False)
        exercise("football-validation-failure", bad_forecast)
        # A staging interruption before atomic rename never alters the pointer.
        (destination / "publication_manifest.json.tmp").write_text('{"interrupted":')
        assert (destination / "publication_manifest.json").read_bytes() == pointer_bytes
        results.append({"case": "interrupted-before-pointer-rename", "result": "retained", "last_good_pointer_unchanged": True})

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/timeout":
                    time.sleep(.2)
                payload = b"corrupt/incomplete response"
                self.send_response(200); self.end_headers()
                try: self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError): pass
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        recovery = SnapshotRecovery()
        old = {"publication_status": "validated", "_publication": original,
               "refreshed_at": original["projection_source_retrieved_at"],
               "injury_freshness_verified": False, "depth_freshness_verified": False}
        recovery.load(2026, 4, old, lambda *args: "complete-last-good-snapshot")
        for label, path, timeout in (("provider-timeout", "/timeout", .03), ("tampered-provider-payload", "/invalid", 1)):
            def loader(*args):
                response = requests.get(f"http://127.0.0.1:{server.server_port}{path}", timeout=timeout)
                from src.publication import verify_file
                verify_file(response.content, original, FILES[0])
            snapshot, metadata, retained = recovery.load(2026, 4, old, loader)
            assert retained and snapshot == "complete-last-good-snapshot"
            assert metadata["refreshed_at"] == old["refreshed_at"]
            results.append({"case": label, "result": "retained", "actual_http_request": True,
                            "last_good_version": metadata["_publication"]["version"], "freshness_timestamp_unchanged": True})
        server.shutdown(); server.server_close()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "scope": "Disposable files and loopback HTTP, not production",
              "tests": results, "remote_last_good_version": original["version"],
              "not_yet_tested": ["stale-provider rejection", "concurrent remote publishers", "Render restart", "browser disconnection"]}
    path = ROOT / "reports/production-certification-20261009/refresh-failure-injection.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
