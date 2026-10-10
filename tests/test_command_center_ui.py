from datetime import datetime, timezone

from dashboard.command_center_v2 import _entry, _kickoff, _ordered_slots


def test_pilot_rejects_previously_open_settings_before_any_repository_call(monkeypatch):
    from dashboard import command_center_v2

    class NoRepositoryAccess:
        def __getattr__(self, name):
            raise AssertionError(f"Pilot settings attempted repository access: {name}")

    notices = []
    monkeypatch.setenv('SDL_RESTRICTED_PILOT', '1')
    monkeypatch.setattr(command_center_v2.st, 'info', notices.append)
    command_center_v2._edit_team_settings({}, NoRepositoryAccess())
    assert notices == ["League settings are fixed for this pilot. Use Manage to edit your lineup."]


NOW = datetime(2026, 10, 8, 18, tzinfo=timezone.utc)


def test_kickoff_uses_nflverse_eastern_time_and_returns_utc():
    kickoff = _kickoff({"gameday": "2026-10-11", "gametime": "13:00"})
    assert kickoff is not None
    assert kickoff.tzinfo == timezone.utc
    assert kickoff.hour == 17


def test_empty_starter_becomes_an_actionable_empty_entry():
    slot = {"id": "slot-1", "slot_type": "FLEX", "slot_order": 0, "is_starter": True, "roster_assignments": []}
    entry = _entry(slot, {}, NOW)
    assert entry["player_id"] is None
    assert entry["availability"] == "Empty"
    assert entry["is_starter"] is True


def test_player_entry_keeps_projection_and_injury_context():
    slot = {"id": "slot-2", "slot_type": "WR", "slot_order": 0, "is_starter": True, "roster_assignments": [{"id": "a1", "player_id": "p1"}]}
    lookup = {"p1": {"player": "Receiver", "median_ppr": 14.2, "gameday": "2026-10-11", "gametime": "13:00", "injury_status_live": "Questionable", "next_opponent": "GB"}}
    entry = _entry(slot, lookup, NOW)
    assert entry["availability"] == "Questionable"
    assert entry["median_ppr"] == 14.2
    assert not entry["game_started"]


def test_roster_slots_use_fantasy_lineup_order_before_bench():
    slots = [
        {"slot_type": "BENCH", "slot_order": 0, "is_starter": False},
        {"slot_type": "FLEX", "slot_order": 0, "is_starter": True},
        {"slot_type": "WR", "slot_order": 1, "is_starter": True},
        {"slot_type": "QB", "slot_order": 0, "is_starter": True},
        {"slot_type": "RB", "slot_order": 1, "is_starter": True},
        {"slot_type": "TE", "slot_order": 0, "is_starter": True},
        {"slot_type": "RB", "slot_order": 0, "is_starter": True},
        {"slot_type": "WR", "slot_order": 0, "is_starter": True},
    ]
    assert [slot["slot_type"] for slot in _ordered_slots(slots)] == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BENCH"]
