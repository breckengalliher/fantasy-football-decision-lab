"""Read a small publication pointer and integrity-check immutable assets."""
import hashlib
import json
import re
import time


def publication_pointer_url(base_url: str, now: float | None = None) -> str:
    """Bound GitHub CDN age without bypassing immutable-asset caching.

    One shared URL per minute, not a unique request per user. GitHub raw
    responses otherwise advertise five minutes of cache lifetime.
    """
    bucket = int((time.time() if now is None else now) // 60)
    return f"{base_url}/publication_manifest.json?sdl_minute={bucket}"


def immutable_base(base_url: str, revision: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Invalid immutable revision")
    # Explicitly support the existing GitHub raw deployment; don't silently
    # invent URL semantics for a future storage provider.
    match = re.fullmatch(
        r"https://raw\.githubusercontent\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/"
        r"([A-Za-z0-9_./-]+)/data/processed/?", base_url
    )
    if not match or any(part in ("", ".", "..") for part in match[3].split("/")):
        raise ValueError("Immutable publication requires the configured GitHub raw base")
    # Keep the configured repository and asset directory. Branch names may
    # contain slashes (isolated QA branches); only the ref is replaced.
    return f"https://raw.githubusercontent.com/{match[1]}/{match[2]}/{revision}/data/processed"


def verified_payload(session, base_url: str, manifest: dict, filename: str) -> bytes:
    if manifest.get("validation_status") != "passed":
        raise ValueError("Unvalidated publication")
    response = session.get(f"{immutable_base(base_url, manifest['revision'])}/{filename}", timeout=(3.05, 12))
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != manifest["files"][filename]["sha256"]:
        raise ValueError("Publication hash mismatch")
    return response.content


def read_metadata(session, base_url: str) -> dict:
    response = session.get(publication_pointer_url(base_url), timeout=(3.05, 8))
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
