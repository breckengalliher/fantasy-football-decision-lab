"""Read a small publication pointer and integrity-check immutable assets."""
import hashlib
import json
import re
import time
import os
from urllib.parse import urlsplit, quote

QA_REPOSITORY = 'breckengalliher/sdl-release-qa-scheduler'


def publication_get(session, url, timeout):
    """Private QA assets use a pinned API destination and per-request credential.

    Never attach this header to the shared HTTP session or follow redirects.
    Public production reads retain their existing behavior.
    """
    parsed = urlsplit(url)
    prefix = '/' + QA_REPOSITORY + '/'
    if parsed.hostname != 'raw.githubusercontent.com' or not parsed.path.startswith(prefix):
        return session.get(url, timeout=timeout)
    if (parsed.scheme != 'https' or parsed.netloc != 'raw.githubusercontent.com'
            or os.getenv('RENDER_SERVICE_ID') != 'srv-db4ir249v7es7389sshg'
            or os.getenv('SUPABASE_URL', '').rstrip('/') != 'https://deburhwrnuqeyexpezzo.supabase.co'):
        raise ValueError('Private snapshot access requires isolated QA service')
    suffix = parsed.path[len(prefix):]
    match = re.fullmatch(r'(qa-app-data|[0-9a-f]{40})/data/processed/([A-Za-z0-9_.-]+)', suffix)
    allowed = {'publication_manifest.json', 'live_refresh_metadata.json', 'live_weekly_current.parquet',
               'live_start_sit_board_4pt_current.parquet', 'live_start_sit_board_6pt_current.parquet'}
    if not match or match[2] not in allowed:
        raise ValueError('Private snapshot path not allowed')
    token = os.getenv('QA_SNAPSHOT_READER_TOKEN', '').strip()
    if not token:
        raise ValueError('Private QA snapshot credential missing')
    endpoint = f'https://api.github.com/repos/{QA_REPOSITORY}/contents/data/processed/{match[2]}?ref={quote(match[1])}'
    response = session.get(endpoint, timeout=timeout, allow_redirects=False,
                           headers={'Authorization': 'Bearer ' + token,
                                    'Accept': 'application/vnd.github.raw+json',
                                    'X-GitHub-Api-Version': '2022-11-28'})
    if 300 <= response.status_code < 400 or response.status_code == 404:
        raise ValueError('Private QA snapshot unavailable; retaining prior snapshot')
    return response


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
    response = publication_get(session, f"{immutable_base(base_url, manifest['revision'])}/{filename}", timeout=(3.05, 12))
    response.raise_for_status()
    if hashlib.sha256(response.content).hexdigest() != manifest["files"][filename]["sha256"]:
        raise ValueError("Publication hash mismatch")
    return response.content


def read_metadata(session, base_url: str) -> dict:
    response = publication_get(session, publication_pointer_url(base_url), timeout=(3.05, 8))
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
    certificate = metadata.get("availability_certificate")
    if isinstance(certificate, dict) and certificate.get("schema_version") == 2:
        from dashboard.availability_evidence import certificate_digest
        certification = manifest.get("availability_certification") or {}
        if (certification.get("status") != "restricted"
                or certification.get("sha256") != certificate_digest(certificate)
                or certificate.get("policy") != "all_availability_actions_blocked"
                or certification.get("all_availability_actions_blocked") is not True
                or metadata.get("injury_freshness_verified") is not False
                or metadata.get("depth_freshness_verified") is not False):
            raise ValueError("Restricted availability publication lacks its safety policy")
        metadata["availability_certification_status"] = "restricted"
    if metadata.get("injury_freshness_verified") is True or metadata.get("depth_freshness_verified") is True:
        from dashboard.availability_evidence import certificate_digest
        from dashboard.availability_evidence import timestamp
        from datetime import datetime, timezone
        certification = manifest.get("availability_certification") or {}
        if (certification.get("status") != "verified"
                or certification.get("sha256") != certificate_digest(metadata.get("availability_certificate"))):
            raise ValueError("Availability freshness lacks a bound certificate")
        until = timestamp(certification.get("valid_until"))
        if not until or until <= datetime.now(timezone.utc):
            metadata["injury_freshness_verified"] = False
            metadata["depth_freshness_verified"] = False
            metadata["availability_certification_status"] = "expired"
    metadata["_publication"] = manifest
    metadata["publication_status"] = "validated"
    return metadata
