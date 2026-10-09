import pytest

from dashboard.repositories.rosters import RosterRepository


class API:
    def __init__(self):
        self.calls = []

    def table(self, token, table, **kwargs):
        self.calls.append((token, table, kwargs))
        return kwargs.get("payload", [])

    def rpc(self, token, function, payload):
        self.calls.append((token, function, {"payload": payload}))


def test_roster_slots_are_scoped_to_authenticated_owner():
    api = API()
    repository = RosterRepository(api, "access", "user-1")
    rows = repository.create_roster_slots("team-1", {"QB": 1, "WR": 2, "BENCH": 1})
    assert len(rows) == 4
    assert all(row["owner_id"] == "user-1" for row in rows)
    assert [row["is_starter"] for row in rows] == [True, True, True, False]


def test_roster_slot_counts_are_bounded():
    repository = RosterRepository(API(), "access", "user-1")
    with pytest.raises(ValueError, match="between 0 and 20"):
        repository.create_roster_slots("team-1", {"BENCH": 21})


def test_unknown_roster_slot_is_rejected():
    repository = RosterRepository(API(), "access", "user-1")
    with pytest.raises(ValueError, match="Unsupported"):
        repository.create_roster_slots("team-1", {"K": 1})


def test_reconcile_adds_slots_with_next_available_order():
    api = API()
    repository = RosterRepository(api, "access", "user-1")
    roster = [{"id": "rb-1", "slot_type": "RB", "slot_order": 0, "roster_assignments": []}]
    repository.reconcile_roster_slots("team-1", roster, {"RB": 2})
    payload = api.calls[-1][2]["payload"]
    assert payload[0]["slot_type"] == "RB"
    assert payload[0]["slot_order"] == 1


def test_reconcile_refuses_to_remove_occupied_slots():
    repository = RosterRepository(API(), "access", "user-1")
    roster = [{"id": "wr-1", "slot_type": "WR", "slot_order": 0, "roster_assignments": [{"id": "a1"}]}]
    with pytest.raises(ValueError, match="Remove players"):
        repository.reconcile_roster_slots("team-1", roster, {"WR": 0})


def test_recording_sync_detection_never_writes_roster_assignments():
    api = API()
    repository = RosterRepository(api, "access", "user-1")
    repository.record_sleeper_result("team-1", "CHANGES_DETECTED", snapshot={"source_hash": "abc"}, changes={"lineup_changed": True})
    assert api.calls == [("access", "record_sleeper_sync_result", {"payload": {"p_team_id": "team-1", "p_status": "CHANGES_DETECTED", "p_snapshot": {"source_hash": "abc"}, "p_changes": {"lineup_changed": True}, "p_error_code": None}})]


def test_applying_sleeper_lineup_requires_explicit_resolution_rpc():
    api = API()
    repository = RosterRepository(api, "access", "user-1")
    plan = [{"slot_id": "slot-1", "player_id": "player-1"}]
    repository.resolve_sleeper_sync("team-1", "APPLY_SLEEPER_LINEUP", plan)
    assert api.calls[-1][1] == "resolve_sleeper_sync"
    assert api.calls[-1][2]["payload"]["p_decision"] == "APPLY_SLEEPER_LINEUP"


def test_swap_is_one_atomic_rpc_and_never_deletes_in_python():
    api = API()
    repo = RosterRepository(api, "access", "user-1")
    repo.swap_players({"id": "a", "slot_id": "qb", "player_id": "p1"}, {"id": "b", "slot_id": "bench", "player_id": "p2"}, "team-1")
    assert len(api.calls) == 1
    assert api.calls[0][1] == "swap_roster_players"
    assert api.calls[0][2]["payload"]["p_first_player"] == "p1"
