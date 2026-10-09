"""Isolated QA publication exercise. No production branch or database writes.

Uses actual provider retrieval, existing football validation, two immutable
commits and one atomic, non-force Git ref update. Credentials remain in the
existing local provider configuration and Git credential manager.
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.publication import FILES, validate_snapshot, write_manifest

BRANCH = "codex/release-cert-190d0608338c"
REMOTE = "https://github.com/breckengalliher/fantasy-football-decision-lab.git"
CHECKOUT = ROOT / "reports/production-certification-20261009/isolated-staging-190d"


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=CHECKOUT, text=True,
                                   stderr=subprocess.STDOUT, timeout=120).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    report_dir = ROOT / "reports/production-certification-20261009"
    receipt = {"started_at": datetime.now(timezone.utc).isoformat(),
               "label": args.label, "scope": "Staging only", "status": "started"}
    receipt_path = report_dir / f"staging-publish-{args.label}.json"
    try:
        if git("branch", "--show-current") != BRANCH or git("remote", "get-url", "origin") != REMOTE:
            raise ValueError("QA branch/remote isolation check failed")
        if git("status", "--porcelain", "--", "data/processed"):
            raise ValueError("Preserve existing unpublished data; checkout is not clean")
        git("fetch", "origin", BRANCH)
        git("merge", "--ff-only", f"origin/{BRANCH}")
        receipt["previous_revision"] = git("rev-parse", "HEAD")
        before = CHECKOUT / "data/processed/publication_manifest.json"
        receipt["before_manifest"] = json.loads(before.read_text()) if before.exists() else None
        # Existing real retrieval command creates a new disposable data folder.
        result = subprocess.run([sys.executable, str(ROOT / "scripts/certify_context_refresh.py")],
                                cwd=ROOT, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError("Provider refresh/football validation failed; no publication")
        evidence = json.loads(result.stdout[result.stdout.index("{"):])
        source = Path(evidence["destination"])
        metadata_path = source / "live_refresh_metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["staging_certification_event"] = {
            "label": args.label, "description": "QA refresh delivery test; real provider retrieval, not an official injury-change claim",
            "retrieved_at": metadata["context_refreshed_at"]}
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        receipt["provider_evidence"] = evidence
        receipt["football_validation"] = validate_snapshot(source)["record_counts"]
        if not args.publish:
            receipt["status"] = "validated-not-published"
        else:
            destination = CHECKOUT / "data/processed"
            for name in FILES:
                shutil.copy2(source / name, destination / name)
            git("add", "-f", *[f"data/processed/{name}" for name in FILES])
            git("commit", "-m", f"QA context delivery {args.label} [skip ci]")
            revision = git("rev-parse", "HEAD")
            for name in FILES:
                committed = subprocess.check_output(["git", "show", f"{revision}:data/processed/{name}"], cwd=CHECKOUT)
                if committed != (destination / name).read_bytes():
                    raise ValueError("Uncommitted publication assets")
            manifest = write_manifest(destination, revision)
            git("add", "-f", "data/processed/publication_manifest.json")
            git("commit", "-m", f"QA validated publication pointer {args.label} [skip ci]")
            # Never force push; concurrent writers cannot replace newer data.
            git("push", "origin", f"HEAD:refs/heads/{BRANCH}")
            receipt.update(status="published", after_manifest=manifest,
                           pointer_commit=git("rev-parse", "HEAD"))
        receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as error:
        # Never capture credential-bearing provider URLs or request bodies.
        receipt.update(status="failed", error_type=type(error).__name__,
                       completed_at=datetime.now(timezone.utc).isoformat())
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path),
                      "version": receipt.get("after_manifest", {}).get("version")}, indent=2))


if __name__ == "__main__":
    main()
