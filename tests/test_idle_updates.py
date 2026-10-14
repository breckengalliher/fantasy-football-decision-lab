from dashboard.live_updates import editing_roster, update_decision


def test_unchanged_pointer_does_not_rerun_or_reload_datasets():
    assert update_decision("v1", {"version": "v1", "validation_status": "passed"}) == "unchanged"


def test_idle_monitor_applies_new_validated_version():
    state = {"cc_selected_team": "test-team", "auth_session": "preserved", "comparison": ["p1", "p2"]}
    before = state.copy()
    assert update_decision("v1", {"version": "v2", "validation_status": "passed"}, command_center=True, state=state) == "apply"
    assert state == before


def test_unsaved_settings_or_player_selection_defers_update():
    for state in ({"cc_selected_team": "t", "cc_team_settings_open": True},
                  {"cc_selected_team": "t", "cc_slot_pick_t_1": "p1"},
                  {"cc_selected_team": "t", "cc_manage_a1": True}):
        before = state.copy()
        assert editing_roster(state)
        assert update_decision("v1", {"version": "v2", "validation_status": "passed"}, command_center=True, state=state) == "defer"
        assert state == before


def test_invalid_or_legacy_pointer_never_triggers_refresh():
    assert update_decision("v1", {}) == "unverified"
    assert update_decision("v1", {"version": "v2", "validation_status": "failed"}) == "unverified"
