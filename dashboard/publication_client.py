"""Read a small publication pointer and integrity-check immutable assets."""
import hashlib
import json
import re


def immutable_base(base_url: str, revision: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid immutable revision")
    # Explicitly support the existing GitHub raw deployment; don't silently
    # invent URL semantics for a future storage provider.
    if not base_url.startswith("https://raw.githubusercontent.com/") or "/main/" not in base_url:
        raise ValueError("Immutable publication requires the configured GitHub raw base")
    return base_url.replace("/main/", f"/{revision}/", 1)


def verified_payload(session, base_url: str, manifest: dict, filename: str) -> bytes:
    if manifest.get("validation_status") != "passed":
        raise ValueError("Unvalidated publication")
    response = session.get(f"{immutable_base(base_url, manifest['revision'])}/{filename}", timeout=(3.05, 12))
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != manifest["files"][filename]["sha256"]:
        raise ValueError("Publication hash mismatch")
    return response.content


def read_metadata(session, base_url: str) -> dict:
    response = session.get(f"{base_url}/publication_manifest.json", timeout=(3.05, 8))
    if response.status_code == 404:
        # Legacy snapshots remain usable but cannot be release-certified.
        legacy = session.get(f"{base_url}/live_refresh_metadata.json", timeout=(3.05, 8))
        legacy.raise_for_status()
        metadata = legacy.json()
        metadata["publication_status"] = "legacy-unverified"
        metadata["injury_freshness_verified"] = False
        metadata["depth_freshness_verified"] = False
        return metadata
    response.raise_for_status()
    manifest = response.json()
    metadata = json.loads(verified_payload(session, base_url, manifest, "live_refresh_metadata.json"))
    if metadata.get("season") != manifest.get("season") or metadata.get("next_week") != manifest.get("week"):
        raise ValueError("Metadata does not match publication")
    metadata["_publication"] = manifest
    metadata["publication_status"] = "validated"
    return metadata
