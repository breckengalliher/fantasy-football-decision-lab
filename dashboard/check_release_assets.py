"""Fail a production build when required runtime assets are missing or unreadable."""
import csv
import json
from pathlib import Path
import pyarrow.parquet as pq

REQUIRED = (
    "data/external/player_identity_crosswalk.csv",
    "data/processed/live_start_sit_board_4pt_current.parquet",
    "data/processed/live_start_sit_board_6pt_current.parquet",
    "data/processed/live_weekly_current.parquet",
    "data/processed/live_refresh_metadata.json",
    "dashboard/assets/sunday-decision-lab-logo-clean.png",
    "dashboard/assets/sunday-decision-lab-icon-clean.png",
    ".streamlit/config.toml",
)


def check_assets(root):
    for name in REQUIRED:
        path = root / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Required release asset missing or empty: {name}")
        if name.endswith(".parquet") and pq.read_metadata(path).num_rows == 0:
            raise ValueError(f"Required release dataset empty: {name}")
        if name.endswith(".png") and path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Required logo is not a PNG: {name}")
    with (root / REQUIRED[0]).open(encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))
    keys = [(r["alias"].strip().casefold(), r["position"]) for r in records]
    if not records or len(keys) != len(set(keys)) or any(not r["gsis_id"] or not r["canonical_name"] for r in records):
        raise ValueError("Release identity crosswalk is empty, incomplete or ambiguous")
    metadata = json.loads((root / "data/processed/live_refresh_metadata.json").read_text())
    if set(metadata.get("refreshed_qb_passing_td_formats", [])) != {4, 6}:
        raise ValueError("Release does not include both supported scoring formats")
    return {"required_assets": len(REQUIRED), "identity_aliases": len(records)}


if __name__ == "__main__":
    print(json.dumps(check_assets(Path(__file__).resolve().parents[1])))
