from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from dashboard.availability_evidence import resolve_availability
from dashboard.lineup_rules import lineup_status
from dashboard.replacement_optimizer import optimize_replacements
from src.availability_certificate import validate_certificate

NOW = datetime(2026, 10, 11, 13, tzinfo=timezone.utc)
KICKOFF = (NOW + timedelta(hours=4)).isoformat()


def event(domain, status, hours=-1, **kwargs):
    return {"player_id": "p", "team": "SEA", "game_id": "g", "domain": domain, "status": status,
            "source_id": domain + status, "authority": "official", "timestamp_basis": "effective",
            "effective_at": (NOW + timedelta(hours=hours)).isoformat(),
            "valid_until": (NOW + timedelta(hours=6)).isoformat(), **kwargs}


def resolve(events, **kwargs):
    return resolve_availability(events, player_id="p", team="SEA", game_id="g", kickoff_at=KICKOFF, now=NOW, **kwargs)


@pytest.mark.parametrize("status", ["out", "questionable", "doubtful", "available"])
def test_current_official_injury_is_not_overridden_by_roster_membership(status):
    result = resolve([event("roster", "active", -.1), event("injury", status)])
    assert result["availability"] == status.title()


def test_inactive_outweighs_later_activation_and_available():
    result = resolve([event("roster", "activated", -.1), event("gameday", "inactive"), event("injury", "available", -.2)])
    assert result["availability"] == "Inactive"
    assert not result["recommendation_allowed"]


@pytest.mark.parametrize("reserve", ["ir", "pup", "nfi", "reserve", "suspended", "exempt"])
def test_reserve_requires_explicit_later_activation(reserve):
    history = [event("roster", reserve, -4), event("roster", "active"), event("injury", "available")]
    assert not resolve(history)["recommendation_allowed"]
    history.append(event("roster", "activated", -.5))
    assert resolve(history)["recommendation_allowed"]


def test_expired_reserve_history_does_not_override_valid_subsequent_activation():
    result = resolve([event("roster", "ir", -48, valid_until=(NOW-timedelta(days=1)).isoformat()),
                      event("roster", "activated"), event("injury", "available")])
    assert result["availability"] == "Available"
    assert result["recommendation_allowed"]


def test_date_precision_is_retained_and_same_day_conflict_blocks():
    reserve = event("roster", "ir", effective_at=None, effective_date="2026-10-08", report_timezone="America/New_York")
    activated = event("roster", "activated", effective_at=None, effective_date="2026-10-09", report_timezone="America/New_York")
    assert resolve([reserve, activated, event("injury", "available")])["recommendation_allowed"]
    activated["effective_date"] = "2026-10-08"
    assert not resolve([reserve, activated, event("injury", "available")])["recommendation_allowed"]
    reserve = event("roster", "ir", effective_at="2026-10-08T14:00:00Z")
    assert not resolve([reserve, activated, event("injury", "available")])["recommendation_allowed"]


@pytest.mark.parametrize("events", [[], [event("roster", "active")],
    [event("roster", "active"), event("injury", "available", effective_at=None)],
    [event("roster", "active"), event("injury", "available", timestamp_basis="retrieved")],
    [event("roster", "active"), event("injury", "available", valid_until=NOW.isoformat())],
    [event("roster", "active"), event("injury", "available", effective_at="2026-10-11T12:00:00")],
    [event("roster", "active"), event("injury", "available", 1)],
    [event("roster", "active"), event("injury", "available"), event("injury", "out")]])
def test_missing_stale_future_or_conflicting_evidence_never_becomes_healthy(events):
    assert resolve(events)["availability"] == "Unknown"
    assert not resolve(events)["recommendation_allowed"]


def test_historical_game_inactive_does_not_govern_current_game():
    assert resolve([event("roster", "active"), event("injury", "available"),
                    event("gameday", "inactive", game_id="last-week")])["recommendation_allowed"]


@pytest.mark.parametrize("state,expected", [("final", "final"), ("in progress", "started"),
    ("postponed", "postponed"), ("cancelled", "postponed")])
def test_game_state_does_not_erase_roster_or_health(state, expected):
    result = resolve([event("roster", "active"), event("injury", "available")], game_status=state)
    assert result["availability"] == "Available" and result["roster_eligibility"] == "active"
    assert result["game_state"] == expected and not result["recommendation_allowed"]


def test_bye_and_clock_lock_are_independent():
    assert resolve([event("roster", "active")], bye=True)["game_state"] == "bye"
    assert resolve_availability([], player_id="p", team="SEA", game_id="g", kickoff_at=NOW.isoformat(), now=NOW)["game_state"] == "started"


@pytest.mark.parametrize("status", ["Reserve", "NFI", "Exempt"])
def test_every_page_gate_rejects_other_reserve_designations(status):
    row = {"player_id": "p", "position": "WR", "slot_type": "WR", "availability": status, "median_ppr": 20,
           "kickoff_at": KICKOFF}
    metadata = {"refreshed_at": NOW.isoformat(), "context_refreshed_at": NOW.isoformat(),
                "injury_freshness_verified": True, "depth_freshness_verified": True}
    assert lineup_status([row], metadata, NOW) == "ACTION REQUIRED"
    assert optimize_replacements([{"slot_id": "s", "slot_type": "WR"}], [row]) == []


@pytest.fixture
def certificate_case():
    events = [event("roster", "active"), event("injury", "available")]
    source = {"url": "https://www.seahawks.com/team/injury-report/", "authority": "official",
              "sha256": "a"*64, "retrieved_at": NOW.isoformat(), "report_at": events[0]["effective_at"],
              "timestamp_basis": "effective"}
    coverage = {"source_id": "injuryavailable", "valid_until": events[0]["valid_until"]}
    certificate = {"schema_version": 1, "season": 2026, "week": 5, "synthetic": False,
        "sources": {e["source_id"]: deepcopy(source) for e in events},
        "players": [{"player_id": "p", "player": "Fixture", "team": "SEA", "position": "WR",
                     "identity_verified": True, "conflicts": [], "events": events,
                     "game": {"game_id": "g", "kickoff_at": KICKOFF, "mapping_verified": True,
                              "bye": False, "opponent": "SF", "source_id": "rosteractive"},
                     "injury_coverage": {**coverage, "complete": True},
                     "depth": {**coverage, "classification": "club_unofficial", "confirmed_starter": False},
                     "inactives": {"state": "not_yet_due", "due_at": (NOW+timedelta(hours=2.5)).isoformat()}}]}
    board = pd.DataFrame([{"player_id": "p", "player": "Fixture", "team": "SEA", "position": "WR",
                           "is_roster_relevant": True, "injury_status_live": "Available", "kickoff_at": KICKOFF,
                           "next_opponent": "SF", "bye_week": False, "game_status_live": "scheduled"}])
    # Synthetic fixture used only locally. Never copied into the real draft or a remote publication.
    return certificate, [board, board.copy()], {"season": 2026, "next_week": 5}


def test_complete_certificate_binds_both_formats_and_next_due_time(certificate_case):
    cert, boards, meta = certificate_case
    result = validate_certificate(cert, boards, meta, NOW)
    assert result["player_count"] == 1 and result["valid_until"] == (NOW+timedelta(hours=2.5)).isoformat()
    with pytest.raises(ValueError, match="Due inactive"):
        validate_certificate(cert, boards, meta, NOW+timedelta(hours=3))


def test_cached_metadata_cannot_outlive_inactive_due_time():
    from dashboard.lineup_rules import critical_data_fresh
    meta = {"refreshed_at": NOW.isoformat(), "context_refreshed_at": NOW.isoformat(),
            "injury_freshness_verified": True, "depth_freshness_verified": True,
            "availability_certificate": {}, "_publication": {"availability_certification": {
                "status": "verified", "valid_until": (NOW+timedelta(seconds=1)).isoformat()}}}
    assert critical_data_fresh(meta, NOW)
    assert not critical_data_fresh(meta, NOW+timedelta(seconds=1))


@pytest.mark.parametrize("damage", ["missing_date", "retrieval_date", "unofficial", "duplicate", "wrong_team", "missing_player",
    "wrong_kickoff", "uncertain_identity", "conflict", "synthetic", "depth_role", "injury_coverage", "unbound_event", "scoring_status",
    "opponent", "bye", "game_state"])
def test_certificate_rejects_unsafe_claims(certificate_case, damage):
    cert, boards, meta = certificate_case
    player = cert["players"][0]
    if damage == "missing_date": cert["sources"]["rosteractive"]["report_at"] = None
    if damage == "retrieval_date": cert["sources"]["rosteractive"]["timestamp_basis"] = "retrieved"
    if damage == "unofficial": cert["sources"]["rosteractive"]["authority"] = "inferred"
    if damage == "duplicate": cert["players"].append(deepcopy(player))
    if damage == "wrong_team": player["team"] = "GB"
    if damage == "missing_player": boards[1].loc[0, "player_id"] = "q"
    if damage == "wrong_kickoff": player["game"]["kickoff_at"] = NOW.isoformat()
    if damage == "uncertain_identity": player["identity_verified"] = False
    if damage == "conflict": player["conflicts"] = ["unresolved"]
    if damage == "synthetic": cert["synthetic"] = True
    if damage == "depth_role": player["depth"]["confirmed_starter"] = True
    if damage == "injury_coverage": player["injury_coverage"]["complete"] = False
    if damage == "unbound_event": player["events"][0]["effective_at"] = NOW.isoformat()
    if damage == "scoring_status": boards[1].loc[0, "injury_status_live"] = "Out"
    if damage == "opponent": boards[1].loc[0, "next_opponent"] = "GB"
    if damage == "bye": boards[1].loc[0, "bye_week"] = True
    if damage == "game_state": player["game"]["status"] = "postponed"
    with pytest.raises(ValueError): validate_certificate(cert, boards, meta, NOW)
