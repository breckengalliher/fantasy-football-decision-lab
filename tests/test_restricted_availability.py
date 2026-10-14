from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pandas as pd
import pytest

from dashboard.lineup_rules import lineup_status
from dashboard.pilot_scope import invited_accounts
from dashboard.publication_client import read_metadata
from dashboard.availability_evidence import certificate_digest
from src.availability_certificate import validate_certificate
from src.context_availability import retain_reviewed_availability

NOW = datetime(2026, 10, 11, 14, tzinfo=timezone.utc)


@pytest.fixture
def case():
    source = {"url": "https://www.nfl.com/schedules/2026/by-week/week-5", "sha256": "a"*64,
              "authority": "official", "retrieved_at": NOW.isoformat(), "timestamp_basis": "undated_observation"}
    game = {"game_id": "g", "kickoff_at": (NOW+timedelta(hours=3)).isoformat(), "bye": False,
            "opponent": "SF", "mapping_verified": True, "source_id": "schedule", "status": "scheduled"}
    record = {"player_id": "p", "player": "Fixture", "team": "SEA", "position": "WR", "identity_verified": True,
              "classification": "UNKNOWN", "conflicts": [], "recommendation_allowed": False, "events": [],
              "depth": {"classification": "unknown", "confirmed_starter": False}, "game": game,
              "inactives": {"state": "not_yet_due", "due_at": (NOW+timedelta(hours=1.5)).isoformat()}}
    cert = {"schema_version": 2, "season": 2026, "week": 5, "synthetic": False,
            "policy": "all_availability_actions_blocked", "sources": {"schedule": source}, "players": [record]}
    meta = {"season": 2026, "next_week": 5, "injury_freshness_verified": False, "depth_freshness_verified": False,
            "availability_certificate": cert, "refreshed_at": NOW.isoformat(), "context_refreshed_at": NOW.isoformat()}
    board = pd.DataFrame([{"player_id": "p", "player": "Fixture", "team": "SEA", "position": "WR",
              "is_roster_relevant": True, "injury_status_live": "Unknown", "game_status_live": "scheduled",
              "bye_week": False, "next_opponent": "SF", "kickoff_at": game["kickoff_at"]}])
    return cert, [board, board.copy()], meta


def test_unknown_is_publishable_only_as_blocked_uncertainty(case):
    cert, boards, meta = case
    result = validate_certificate(cert, boards, meta, NOW)
    assert result["status"] == "restricted" and result["unknown_count"] == 1
    meta["_publication"] = {"availability_certification": result}
    assert lineup_status([{"player_id": "p", "availability": "Available", "kickoff_at": boards[0].iloc[0].kickoff_at}], meta, NOW) == "VERIFY DATA"


@pytest.mark.parametrize("fault", ["freshness", "policy", "recommendation", "verified_unknown", "starter", "opponent", "status", "identity", "time", "missing_event_time", "forged_event", "scoring_mismatch"])
def test_restricted_publication_rejects_unsupported_claims(case, fault):
    cert, boards, meta = case
    player = cert["players"][0]
    if fault == "freshness": meta["injury_freshness_verified"] = True
    elif fault == "policy": cert["policy"] = "allow_available"
    elif fault == "recommendation": player["recommendation_allowed"] = True
    elif fault == "verified_unknown": player["classification"] = "VERIFIED"
    elif fault == "starter": player["depth"]["confirmed_starter"] = True
    elif fault == "opponent": player["game"]["opponent"] = "ARI"
    elif fault == "status": boards[0]["injury_status_live"] = "Available"
    elif fault == "identity": player["team"] = "GB"
    elif fault == "time": cert["sources"]["schedule"]["retrieved_at"] = (NOW+timedelta(hours=1)).isoformat()
    elif fault in {"missing_event_time", "forged_event"}:
        player["events"] = [{"source_id": "schedule", "authority": "official", "timestamp_basis": "published",
                              "effective_at": NOW.isoformat() if fault == "forged_event" else None}]
    elif fault == "scoring_mismatch": boards[1]["injury_status_live"] = "Out"
    with pytest.raises(ValueError): validate_certificate(cert, boards, meta, NOW)


def test_pending_inactives_do_not_remain_future_after_due(case):
    cert, boards, meta = case
    with pytest.raises(ValueError, match="expired"):
        validate_certificate(cert, boards, meta, NOW+timedelta(hours=2))
    cert["players"][0]["inactives"]["state"] = "due_missing"
    assert validate_certificate(cert, boards, meta, NOW+timedelta(hours=2))["status"] == "restricted"


def test_context_refresh_cannot_overwrite_reviewed_unknown_or_source_timestamps(case):
    cert, original, meta = case
    originals = {4: original[0], 6: original[1]}
    incoming = {p: frame.assign(injury_status_live="Available", depth_order_live=1,
                  game_status_live="InProgress", spread_line_live=-3.) for p, frame in originals.items()}
    before = deepcopy(meta)
    boards, after = retain_reviewed_availability(incoming, originals, meta, NOW)
    assert meta == before
    assert after["availability_certificate"]["sources"] == before["availability_certificate"]["sources"]
    assert after["context_refreshed_at"] == before["context_refreshed_at"]
    for board in boards.values():
        assert board.iloc[0].injury_status_live == "Unknown"
        assert pd.isna(board.iloc[0].depth_order_live)
        assert board.iloc[0].game_status_live == "scheduled"
        assert board.iloc[0].spread_line_live == -3.
    assert not after["injury_freshness_verified"] and not after["depth_freshness_verified"]


def test_context_refresh_downgrades_due_inactive_claim_without_new_evidence(case):
    cert, original, meta = case
    cert["players"][0]["classification"] = "PENDING OFFICIAL REPORT"
    originals = {4: original[0], 6: original[1]}
    _, still_pending = retain_reviewed_availability(originals, originals, meta, NOW)
    assert still_pending["availability_certificate"]["players"][0]["classification"] == "PENDING OFFICIAL REPORT"
    boards, after = retain_reviewed_availability(originals, originals, meta, NOW+timedelta(hours=2))
    assert after["availability_certificate"]["players"][0]["inactives"]["state"] == "due_missing"
    assert after["availability_certificate"]["players"][0]["classification"] == "UNKNOWN"
    assert after["availability_certificate"]["sources"] == cert["sources"]
    assert validate_certificate(after["availability_certificate"], list(boards.values()), after,
                                NOW+timedelta(hours=2))["status"] == "restricted"


def test_context_refresh_rejects_changed_identity_before_publication(case):
    cert, original, meta = case
    originals = {4: original[0], 6: original[1]}
    incoming = {4: original[0].assign(team="ARI"), 6: original[1]}
    with pytest.raises(ValueError, match="identity or scope changed"):
        retain_reviewed_availability(incoming, originals, meta, NOW)


@pytest.mark.parametrize("database,allowed", [("https://deburhwrnuqeyexpezzo.supabase.co", True),
                                            ("https://production.supabase.co", False), ("", False)])
def test_mutable_pointer_is_confined_to_named_qa_database(database, allowed):
    env = {"SDL_RESTRICTED_PILOT": "1", "SDL_PILOT_ACCOUNT_IDS": ",".join(str(UUID(int=i)) for i in range(1,5)),
           "SUPABASE_URL": database,
           "SNAPSHOT_BASE_URL": "https://raw.githubusercontent.com/breckengalliher/fantasy-football-decision-lab/codex/qa-availability-data/data/processed"}
    if allowed: assert len(invited_accounts(env)) == 4
    else:
        with pytest.raises(ValueError, match="immutable"): invited_accounts(env)


def test_runtime_rejects_tampered_restricted_policy(case, monkeypatch):
    cert, boards, meta = case
    manifest = {"season": 2026, "week": 5, "availability_certification": validate_certificate(cert, boards, meta, NOW)}
    import json
    import dashboard.publication_client as client
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return manifest
    class Session:
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr(client, "verified_payload", lambda *a: json.dumps(meta).encode())
    assert read_metadata(Session(), "https://example.test")["availability_certification_status"] == "restricted"
    meta["injury_freshness_verified"] = True
    with pytest.raises(ValueError, match="safety policy"): read_metadata(Session(), "https://example.test")
