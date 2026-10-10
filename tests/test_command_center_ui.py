from datetime import datetime, timezone

import pytest

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


@pytest.mark.parametrize('write_succeeds', [True, False])
def test_save_acknowledgement_requires_database_commit(monkeypatch, write_succeeds):
    from dashboard import command_center_v2

    events = []
    current = {'id': 'assignment-a', 'player_id': 'player-a'}
    other = {'id': 'assignment-b', 'player_id': 'player-b'}
    source = {'id': 'source', 'slot_type': 'BENCH', 'slot_order': 1,
              'roster_assignments': [current]}
    target = {'id': 'target', 'slot_type': 'BENCH', 'slot_order': 2,
              'roster_assignments': [other]}

    class Column:
        def button(self, *args, **kwargs):
            return False

    class Screen:
        session_state = {'cc_manage_assignment-a': True,
                         'cc_target_assignment-a': 'target'}

        def caption(self, *args, **kwargs):
            pass

        def columns(self, *args, **kwargs):
            return [Column(), Column()]

        def checkbox(self, *args, **kwargs):
            return False

        def selectbox(self, label, values, **kwargs):
            return values[0]

        def button(self, *args, **kwargs):
            return True

        def toast(self, message):
            events.append(('ack', message))

        def rerun(self):
            events.append(('rerun', None))

        def error(self, message):
            events.append(('error', message))

    class Repository:
        def swap_players(self, *args):
            if not write_succeeds:
                raise ValueError('Save rejected: stale edit')
            events.append(('committed', None))

    screen = Screen()
    monkeypatch.setattr(command_center_v2, 'st', screen)
    monkeypatch.setattr(command_center_v2, 'edit_is_current', lambda *args: True)
    command_center_v2._manage_player(
        {'id': 'team'}, [source, target], source, current, Repository(), None,
        {'player-a': {'position': 'QB'}, 'player-b': {'position': 'QB'}},
    )
    if write_succeeds:
        assert events == [('committed', None), ('ack', 'Lineup saved'), ('rerun', None)]
        assert screen.session_state['cc_manage_assignment-a'] is False
        assert 'cc_target_assignment-a' not in screen.session_state
    else:
        assert events == [('error', 'Save rejected: stale edit')]
        assert screen.session_state['cc_manage_assignment-a'] is True


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
