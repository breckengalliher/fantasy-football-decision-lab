"""Two independent QA publishers compete for one non-force branch update."""
import concurrent.futures
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.publication import FILES, write_manifest
from scripts.publish_staging_context import BRANCH, CHECKOUT, REMOTE


def run(directory, *args):
    result = subprocess.run(["git", *args], cwd=directory, capture_output=True, text=True, timeout=90)
    if result.returncode: raise RuntimeError("Git operation failed")
    return result.stdout.strip()


def main():
    run(CHECKOUT, "fetch", "origin", BRANCH)
    run(CHECKOUT, "merge", "--ff-only", f"origin/{BRANCH}")
    barrier = threading.Barrier(2)
    with tempfile.TemporaryDirectory(prefix="qa-publishers-", dir=ROOT / "reports") as temporary:
        def publisher(index):
            directory = Path(temporary) / str(index)
            result = subprocess.run(["git", "clone", "--no-hardlinks", str(CHECKOUT), str(directory)], capture_output=True, timeout=90)
            if result.returncode: raise RuntimeError("QA clone failed")
            run(directory, "remote", "set-url", "origin", REMOTE)
            run(directory, "config", "user.name", "SDL QA Certification")
            run(directory, "config", "user.email", "qa-certification@example.invalid")
            processed = directory / "data/processed"
            metadata_file = processed / FILES[-1]
            metadata = json.loads(metadata_file.read_text())
            metadata["staging_certification_event"] = {
                "label": f"concurrent-publisher-{index}",
                "description": "QA concurrency test, same real provider retrieval and projections"}
            metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            run(directory, "add", "-f", "data/processed/live_refresh_metadata.json")
            run(directory, "commit", "-m", f"QA concurrent publisher {index} data [skip ci]")
            revision = run(directory, "rev-parse", "HEAD")
            manifest = write_manifest(processed, revision)
            run(directory, "add", "-f", "data/processed/publication_manifest.json")
            run(directory, "commit", "-m", f"QA concurrent publisher {index} pointer [skip ci]")
            barrier.wait(timeout=60)
            pushed = subprocess.run(["git", "push", "origin", f"HEAD:refs/heads/{BRANCH}"], cwd=directory, capture_output=True, text=True, timeout=90)
            return {"publisher": index, "pushed": pushed.returncode == 0,
                    "version": manifest["version"], "revision": revision,
                    "pointer_commit": run(directory, "rev-parse", "HEAD")}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(publisher, (1, 2)))
        assert sum(r["pushed"] for r in results) == 1, "Expected exactly one non-force winner"
    winner = next(r for r in results if r["pushed"])
    run(CHECKOUT, "fetch", "origin", BRANCH)
    run(CHECKOUT, "merge", "--ff-only", f"origin/{BRANCH}")
    pointer = json.loads((CHECKOUT / "data/processed/publication_manifest.json").read_text())
    assert pointer["version"] == winner["version"]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "scope": "Approved QA branch only",
              "publishers": results, "result": "One validated publication wins; conflicting ref update rejected",
              "last_good_version": pointer["version"], "projection_timestamp": pointer["projection_source_retrieved_at"]}
    output = ROOT / "reports/production-certification-20261009/concurrent-publication.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
