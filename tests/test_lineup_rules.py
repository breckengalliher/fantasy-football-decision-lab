from datetime import datetime, timedelta, timezone

from dashboard.lineup_rules import build_lineup_actions, lineup_status


NOW = datetime(2026, 10, 11, 15, tzinfo=timezone.utc)
FRESH = {"refreshed_at": NOW.isoformat(), "context_refreshed_at": NOW.isoformat(),
         "injury_freshness_verified": True, "depth_freshness_verified": True}


def test_ready_requires_fresh_critical_data():
    starter = {"player_id": "p1", "slot_type": "WR", "availability": "", "kickoff_at": (NOW + timedelta(hours=5)).isoformat()}
    assert lineup_status([starter], FRESH, NOW) == "READY"
    assert lineup_status([starter], {}, NOW) == "VERIFY DATA"


def test_unavailable_and_empty_starters_are_mandatory_and_prioritized():
    starters = [
        {"player_id": "p1", "slot_type": "WR", "availability": "Questionable", "kickoff_at": (NOW + timedelta(hours=8)).isoformat()},
        {"player_id": None, "slot_type": "RB", "kickoff_at": (NOW + timedelta(hours=2)).isoformat()},
        {"player_id": "p2", "slot_type": "TE", "availability": "Out", "kickoff_at": (NOW + timedelta(hours=3)).isoformat()},
    ]
    actions = build_lineup_actions(starters, NOW)
    assert actions[0].mandatory and actions[1].mandatory
    assert {actions[0].slot_type, actions[1].slot_type} == {"RB", "TE"}
    assert lineup_status(starters, FRESH, NOW) == "INCOMPLETE SETUP"


def test_questionable_near_kickoff_becomes_urgent_without_being_confirmed_out():
    starters = [{"player_id": "p1", "slot_type": "WR", "availability": "Questionable", "kickoff_at": (NOW + timedelta(minutes=45)).isoformat()}]
    action = build_lineup_actions(starters, NOW)[0]
    assert action.severity == "urgent"
    assert not action.mandatory


def test_ready_cannot_hide_missing_schedule_or_empty_setup():
    assert lineup_status([], FRESH, NOW) == "INCOMPLETE SETUP"
    assert lineup_status([{"player_id": "p1"}], FRESH, NOW) == "VERIFY DATA"


def test_out_overrides_started_game_and_injury_has_distinct_state():
    kickoff = (NOW + timedelta(hours=4)).isoformat()
    out = {"player_id": "p1", "slot_type": "WR", "availability": "Out", "kickoff_at": kickoff}
    started = {"player_id": "p2", "slot_type": "RB", "game_started": True, "kickoff_at": kickoff}
    assert lineup_status([out, started], FRESH, NOW) == "ACTION REQUIRED"
    assert lineup_status([{**out, "availability": "Questionable"}], FRESH, NOW) == "INJURY CONCERN"


def test_future_refresh_timestamp_is_not_fresh():
    future = {"refreshed_at": (NOW + timedelta(days=1)).isoformat(), "context_refreshed_at": NOW.isoformat()}
    assert lineup_status([{"player_id": "p", "kickoff_at": (NOW + timedelta(hours=1)).isoformat()}], future, NOW) == "VERIFY DATA"


def test_recent_download_without_source_freshness_is_not_ready():
    starter = {"player_id": "p", "kickoff_at": (NOW + timedelta(hours=1)).isoformat()}
    retrieved = {"refreshed_at": NOW.isoformat(), "context_refreshed_at": NOW.isoformat()}
    assert lineup_status([starter], retrieved, NOW) == "VERIFY DATA"
    assert lineup_status([starter], {**FRESH, "depth_freshness_verified": False}, NOW) == "VERIFY DATA"

