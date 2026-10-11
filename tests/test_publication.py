import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.publication import FILES, build_manifest, verify_file, write_manifest
from dashboard.publication_client import immutable_base, read_metadata, verified_payload
from dashboard.football_integrity import guard_forecasts
from dashboard.publication_client import publication_pointer_url


def test_pointer_cache_busting_is_shared_and_assets_remain_immutable():
    base = "https://raw.githubusercontent.com/owner/repo/qa/data/processed"
    assert publication_pointer_url(base, 120) == publication_pointer_url(base, 179)
    assert publication_pointer_url(base, 180) != publication_pointer_url(base, 179)
    assert immutable_base(base, "a" * 40).endswith("/data/processed")


@pytest.fixture
def snapshot(tmp_path):
    metadata = {"season": 2026, "next_week": 5, "refreshed_qb_passing_td_formats": [4, 6],
                "refreshed_at": "2026-10-09T12:00:00+00:00"}
    (tmp_path / FILES[-1]).write_text(json.dumps(metadata), encoding="utf-8")
    board = pd.DataFrame([{"player_id": "gsis-1", "player": "Example", "position": "WR",
                           "team": "SEA", "floor_ppr": 8., "median_ppr": 14.,
                           "ceiling_ppr": 22., "projected_ppr": 14.}])
    for filename in FILES[:2]:
        board.to_parquet(tmp_path / filename, index=False)
    pd.DataFrame([{"player_id": "gsis-1", "week": 1, "ppr": 10.}]).to_parquet(tmp_path / FILES[2], index=False)
    return tmp_path


def test_complete_manifest_binds_all_files_and_unknown_source_freshness(snapshot):
    manifest = build_manifest(snapshot, "a" * 40)
    assert manifest["validation_status"] == "passed"
    assert manifest["source_freshness"] == {"injury": "unverified", "depth": "unverified"}
    assert manifest["availability_source_updated_at"] is None
    for filename in FILES:
        verify_file((snapshot / filename).read_bytes(), manifest, filename)


def test_invalid_forecast_never_replaces_existing_pointer(snapshot):
    before = write_manifest(snapshot, "a" * 40)
    pointer = snapshot / "publication_manifest.json"
    board = pd.read_parquet(snapshot / FILES[0])
    board.loc[0, "median_ppr"] = -1
    board.to_parquet(snapshot / FILES[0], index=False)
    with pytest.raises(ValueError, match="validation failed"):
        write_manifest(snapshot, "b" * 40)
    assert json.loads(pointer.read_text()) == before


def test_partial_or_tampered_publication_is_rejected(snapshot):
    manifest = build_manifest(snapshot, "a" * 40)
    with pytest.raises(ValueError, match="does not match"):
        verify_file(b"incomplete download", manifest, FILES[0])
    (snapshot / FILES[2]).unlink()
    with pytest.raises(FileNotFoundError):
        write_manifest(snapshot, "b" * 40)


def test_unchanged_data_has_stable_version(snapshot):
    first = build_manifest(snapshot, "a" * 40)
    later = build_manifest(snapshot, "b" * 40, datetime(2026, 10, 10, tzinfo=timezone.utc))
    assert first["version"] == later["version"]
    assert first["revision"] != later["revision"]


def test_client_downloads_pinned_revision_and_rejects_hash_mismatch(snapshot):
    manifest = build_manifest(snapshot, "a" * 40)
    urls = []
    class Response:
        status_code = 200
        def __init__(self, payload): self.content = payload
        def raise_for_status(self): pass
        def json(self): return json.loads(self.content)
    class Session:
        def get(self, url, **kwargs):
            urls.append(url)
            if url.split("?")[0].endswith("publication_manifest.json"):
                return Response(json.dumps(manifest).encode())
            return Response((snapshot / url.rsplit("/", 1)[-1]).read_bytes())
    base = "https://raw.githubusercontent.com/owner/repo/main/data/processed"
    metadata = read_metadata(Session(), base)
    assert metadata["_publication"]["version"] == manifest["version"]
    assert f"/{'a' * 40}/" in urls[-1]
    manifest["files"][FILES[0]]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        verified_payload(Session(), base, manifest, FILES[0])


def test_scoring_identity_mismatch_blocks_publication(snapshot):
    board = pd.read_parquet(snapshot / FILES[1])
    board.loc[0, "player_id"] = "another-player"
    board.to_parquet(snapshot / FILES[1], index=False)
    with pytest.raises(ValueError, match="disagree"):
        write_manifest(snapshot, "a" * 40)


@pytest.mark.parametrize("ref", ["main", "codex/release-cert-8306b4bb83ca", "b" * 40])
def test_immutable_publication_preserves_repository_for_isolated_refs(ref):
    base = f"https://raw.githubusercontent.com/owner/repo/{ref}/data/processed"
    assert immutable_base(base, "a" * 40) == (
        f"https://raw.githubusercontent.com/owner/repo/{'a' * 40}/data/processed"
    )


@pytest.mark.parametrize("base", [
    "https://example.com/owner/repo/main/data/processed",
    "https://raw.githubusercontent.com.evil.test/owner/repo/main/data/processed",
    "https://raw.githubusercontent.com/owner/repo/main/../data/processed",
    "https://raw.githubusercontent.com/owner/repo/main/data/processed?token=x",
])
def test_immutable_publication_rejects_ambiguous_or_external_bases(base):
    with pytest.raises(ValueError):
        immutable_base(base, "a" * 40)


def test_invalid_baseline_can_only_publish_as_explicit_nonactionable_quarantine(snapshot):
    for filename in FILES[:2]:
        board = pd.read_parquet(snapshot / filename)
        board.loc[0, ["median_ppr", "projected_ppr"]] = -0.1
        guarded = guard_forecasts(board)
        assert guarded.loc[0, "median_ppr"] == -0.1
        guarded.to_parquet(snapshot / filename, index=False)
    manifest = build_manifest(snapshot, "a" * 40)
    assert manifest["validation_status"] == "passed"
    board = pd.read_parquet(snapshot / FILES[0])
    board["is_roster_relevant"] = True
    board.to_parquet(snapshot / FILES[0], index=False)
    with pytest.raises(ValueError, match="validation failed"):
        write_manifest(snapshot, "b" * 40)


@pytest.mark.parametrize("flag", ["injury_freshness_verified", "depth_freshness_verified"])
def test_unproven_freshness_never_advances_last_good_pointer(snapshot, flag):
    before = write_manifest(snapshot, "a" * 40)
    metadata = json.loads((snapshot / FILES[-1]).read_text())
    metadata[flag] = True
    (snapshot / FILES[-1]).write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="Availability certificate"):
        write_manifest(snapshot, "b" * 40)
    assert json.loads((snapshot / "publication_manifest.json").read_text()) == before


def test_interruption_before_atomic_replace_retains_last_good_pointer(snapshot, monkeypatch):
    before = write_manifest(snapshot, "a" * 40)
    original = Path.replace
    def interrupted(path, target):
        if path.name == "publication_manifest.json.tmp":
            raise OSError("simulated interrupted publication")
        return original(path, target)
    monkeypatch.setattr(Path, "replace", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        write_manifest(snapshot, "b" * 40)
    assert json.loads((snapshot / "publication_manifest.json").read_text()) == before
    monkeypatch.setattr(Path, "replace", original)
    retry = write_manifest(snapshot, "b" * 40)
    assert retry["version"] == before["version"]
    assert retry["availability_source_updated_at"] == before["availability_source_updated_at"]


@pytest.mark.parametrize("expiry,expected", [("2099-01-01T00:00:00Z", True), ("2000-01-01T00:00:00Z", False)])
def test_verified_client_path_needs_only_packaged_dashboard_modules(monkeypatch, expiry, expected):
    import builtins
    import hashlib
    from dashboard.availability_evidence import certificate_digest
    cert = {"fixture": "client-contract-only; never published"}
    meta = {"season": 2026, "next_week": 5, "injury_freshness_verified": True,
            "depth_freshness_verified": True, "availability_certificate": cert}
    payload = json.dumps(meta).encode()
    manifest = {"validation_status": "passed", "revision": "a"*40, "season": 2026, "week": 5,
                "files": {"live_refresh_metadata.json": {"sha256": hashlib.sha256(payload).hexdigest()}},
                "availability_certification": {"status": "verified", "sha256": certificate_digest(cert), "valid_until": expiry}}
    class Response:
        status_code = 200
        def __init__(self, content): self.content = content
        def json(self): return json.loads(self.content)
        def raise_for_status(self): pass
    class Session:
        def get(self, url, **kwargs):
            return Response(json.dumps(manifest).encode() if 'publication_manifest.json' in url else payload)
    original = builtins.__import__
    def packaged_import(name, *args, **kwargs):
        if name == "src" or name.startswith("src."):
            raise ModuleNotFoundError("Build-time src modules are not in the web image")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", packaged_import)
    result = read_metadata(Session(), "https://raw.githubusercontent.com/owner/repo/qa/data/processed")
    assert result["injury_freshness_verified"] is expected
    assert result["depth_freshness_verified"] is expected
