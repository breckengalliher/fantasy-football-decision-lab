from copy import deepcopy
from types import SimpleNamespace

import pytest
import requests
from streamlit.testing.v1 import AppTest

from dashboard.repositories.rosters import RosterRepository
from dashboard.supabase_api import SupabaseAPI, SupabaseAPIError


COUNTS = dict(QB=1, RB=0, WR=0, TE=0, FLEX=0, SUPERFLEX=0, BENCH=1)
TEAM = dict(id="team-a", league_id="league-a", name="Team A", updated_at="2026-10-15T10:00:00Z",
            fantasy_leagues=dict(name="League A", passing_td_points=4, updated_at="2026-10-15T10:00:00Z"))
ROSTER = [dict(id="slot-qb", slot_type="QB", slot_order=0, is_starter=True,
               roster_assignments=[dict(id="assignment-1", player_id="player-1", updated_at="version-1")]),
          dict(id="slot-bench", slot_type="BENCH", slot_order=0, is_starter=False, roster_assignments=[])]


class API:
    def __init__(self, result=None):
        self.calls = []
        self.result = {"saved": True} if result is None else result

    def rpc(self, token, function, payload):
        self.calls.append((token, function, payload))
        return self.result

    def table(self, *args, **kwargs):
        raise AssertionError("Settings must use one atomic RPC, never table writes")


def save(repo, **kwargs):
    values = dict(name="Updated league", team_name="Updated team", passing_td_points=6, slot_counts=dict(COUNTS))
    values.update(kwargs)
    repo.save_team_settings(TEAM, ROSTER, **values)


def test_settings_use_one_rpc_without_assignments_or_owner_input():
    before = deepcopy((TEAM, ROSTER))
    api = API()
    save(RosterRepository(api, "ordinary-user-token", "owner-a"))
    assert len(api.calls) == 1
    token, function, payload = api.calls[0]
    assert function == "save_team_settings"
    assert payload["p_team_id"] == "team-a"
    assert payload["p_expected"]["league_id"] == "league-a"
    assert payload["p_expected"]["slots"][0]["id"] == "slot-bench"
    assert "owner" not in str(payload) and "assignment-1" not in str(payload)
    assert (TEAM, ROSTER) == before


@pytest.mark.parametrize("kwargs", [
    dict(name=" "), dict(team_name="x"*81), dict(passing_td_points=5),
    dict(passing_td_points=True), dict(slot_counts={**COUNTS, "K": 1}),
    dict(slot_counts={**COUNTS, "BENCH": -1}), dict(slot_counts={**COUNTS, "BENCH": 21}),
    dict(slot_counts={**COUNTS, "BENCH": 1.5}), dict(slot_counts={**COUNTS, "BENCH": True}),
    dict(slot_counts={**COUNTS, "QB": 0}), dict(slot_counts={key: 0 for key in COUNTS}),
])
def test_invalid_or_occupied_reductions_never_write(kwargs):
    api = API()
    with pytest.raises(ValueError):
        save(RosterRepository(api, "token", "owner-a"), **kwargs)
    assert api.calls == []


def test_missing_revision_and_unconfirmed_commit_do_not_acknowledge():
    api = API(result={})
    with pytest.raises(SupabaseAPIError, match="not confirmed"):
        save(RosterRepository(api, "token", "owner-a"))
    team = deepcopy(TEAM)
    team["fantasy_leagues"].pop("updated_at")
    with pytest.raises(ValueError, match="reopen"):
        RosterRepository(api, "token", "owner-a").save_team_settings(team, ROSTER,
            name="L", team_name="T", passing_td_points=4, slot_counts=COUNTS)
    assert len(api.calls) == 1


@pytest.mark.parametrize("message,visible", [
    ("Settings changed. Close League Settings and reopen it before saving.", "Settings changed."),
    ("private sql table contents secret", "League settings were not saved."),
])
def test_settings_errors_sanitized(message, visible):
    api = SupabaseAPI("https://example.invalid", "public-key")
    response = requests.Response()
    response.status_code = 400
    import json
    response._content = json.dumps({"message": message}).encode()
    api.http = SimpleNamespace(request=lambda *args, **kwargs: response)
    with pytest.raises(SupabaseAPIError, match=visible):
        api.rpc("user-token", "save_team_settings", {})


HARNESS = """
import streamlit as st
from copy import deepcopy
from dashboard.command_center_v2 import _league_settings_panel
from tests.test_league_settings import TEAM, ROSTER
if "teams" not in st.session_state:
    b=deepcopy(TEAM); b.update(id="team-b", league_id="league-b", name="Team B")
    b["fantasy_leagues"]["name"]="League B"
    st.session_state.teams={"team-a":deepcopy(TEAM),"team-b":b}
    st.session_state.calls=[]
class Repo:
    def team_roster(self, team_id): return deepcopy(ROSTER)
    def save_team_settings(self, team, roster, **kwargs):
        if st.session_state.get("reject",False): raise ValueError("Concurrent settings change")
        st.session_state.calls.append((deepcopy(team),deepcopy(roster),kwargs))
        saved=st.session_state.teams[team["id"]]
        saved["name"]=kwargs["team_name"]
        saved["fantasy_leagues"]["name"]=kwargs["name"]
        saved["fantasy_leagues"]["passing_td_points"]=kwargs["passing_td_points"]
selected=st.selectbox("Team",["team-a","team-b"])
_league_settings_panel(st.session_state.teams[selected],Repo())
"""


def test_form_saves_only_selected_team_and_preserves_lineup(monkeypatch):
    monkeypatch.setenv("SDL_RESTRICTED_PILOT", "1")
    app = AppTest.from_string(HARNESS).run()
    assert not app.exception
    app.button[0].click().run()
    assert len(app.number_input) == 7
    app.text_input(key="cc_edit_team-a_name").set_value("Renamed A")
    app.radio[0].set_value(6)
    app.number_input(key="cc_edit_team-a_BENCH").set_value(2)
    app.button[-1].click().run()
    assert not app.exception
    assert len(app.session_state.calls) == 1
    team, roster, values = app.session_state.calls[0]
    assert team["id"] == "team-a" and roster == ROSTER
    assert values["passing_td_points"] == 6 and values["slot_counts"]["BENCH"] == 2
    assert app.session_state.teams["team-b"]["name"] == "Team B"
    assert app.session_state.teams["team-b"]["fantasy_leagues"]["passing_td_points"] == 4
    assert "saved" in app.success[0].value


def test_original_revision_survives_rerun_failed_save_and_team_switch():
    app = AppTest.from_string(HARNESS).run()
    app.button[0].click().run()
    app.text_input(key="cc_edit_team-a_name").set_value("Draft A")
    app.session_state.teams["team-a"]["updated_at"] = "new-server-revision"
    app.session_state["reject"] = True
    app.button[-1].click().run()
    assert not app.exception and app.error
    assert not app.success and app.session_state.calls == []
    assert app.session_state["cc_settings_draft_team-a"]["team"]["updated_at"] == TEAM["updated_at"]
    app.selectbox[0].select("team-b").run()
    assert len(app.text_input) == 0
    app.button[0].click().run()
    assert app.text_input(key="cc_edit_team-b_name").value == "Team B"
    assert app.session_state.calls == []


def test_cancel_discards_draft_without_saving():
    app = AppTest.from_string(HARNESS).run()
    app.button[0].click().run()
    app.text_input(key="cc_edit_team-a_name").set_value("Discard")
    app.button[0].click().run()
    assert app.session_state.calls == []
    app.button[0].click().run()
    assert app.text_input(key="cc_edit_team-a_name").value == "Team A"
