"""Archive and fingerprint application sources and packaged public data only.

Never archive secrets, account state, environment files, caches, or QA reports.
The hash identifies a dirty-tree candidate; HEAD alone does not identify it.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
from datetime import datetime, timezone
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "reports/production-certification-20261009"
PREFIXES = ("dashboard/", "src/", "tests/", "scripts/", ".github/workflows/", "supabase/migrations/")
ROOT_FILES = {"Dockerfile", "render.yaml", "requirements.txt", "pyproject.toml", ".dockerignore", ".streamlit/config.toml", "config/league.json"}


def candidate_files():
    tracked = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    names = {n for n in tracked if n and (n.startswith(PREFIXES) or n in ROOT_FILES)}
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "data/processed").glob("*") if p.is_file())
    names.add("data/external/player_identity_crosswalk.csv")
    return sorted(n for n in names if "__pycache__" not in n and not any(part in n.casefold() for part in ("secret", ".env", "token")))


def main():
    files = {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in candidate_files()}
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    identifier = "sdl-rc-20261009-" + fingerprint[:12]
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / f"{identifier}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        for name in files:
            handle.write(ROOT / name, name)
    versions = {}
    for package in ("streamlit", "streamlit-local-storage", "pandas", "pyarrow", "requests", "numpy"):
        versions[package] = importlib.metadata.version(package)
    manifest = {"candidate_id": identifier, "base_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
                "working_tree_clean": False, "source_and_asset_sha256": fingerprint,
                "created_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
                "dependencies": versions, "files": files, "rollback_archive": archive.name,
                "scope": "Application sources and public packaged assets; no secrets or private user records"}
    (DEST / "candidate.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, indent=2))


if __name__ == "__main__":
    main()
