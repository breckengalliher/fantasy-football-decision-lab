"""Local workflow helper. Never triggers jobs or pushes to GitHub."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.publication import FILES, validate_snapshot, write_manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    processed = ROOT / "data/processed"
    if args.validate_only:
        validate_snapshot(processed)
        print("Complete snapshot validation passed")
    else:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        for filename in FILES:
            committed = subprocess.check_output(["git", "show", f"{revision}:data/processed/{filename}"], cwd=ROOT)
            if committed != (processed / filename).read_bytes():
                raise ValueError("Publication files must exactly match the immutable data commit")
        manifest = write_manifest(processed, revision)
        print(f"Prepared immutable publication {manifest['version'][:12]}")


if __name__ == "__main__":
    main()
