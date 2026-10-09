from types import SimpleNamespace

from dashboard.sleeper_sync import build_snapshot, detect_changes, snapshot_hash


def snapshot(players=("1", "2", "3"), starters=("1", "2"), *, positions=("QB", "RB", "BN"), scoring=None, unmatched=()):
    scoring = scoring or {"pass_td": 4, "rec": 1}
    mappings = [
        {"external_player_id": value, "player_id": f"gsis-{value}", "name": f"Player {value}", "matched": value not in unmatched}
        for value in players
    ]
    for row in mappings:
        if not row["matched"]:
            row["player_id"] = None
    league = SimpleNamespace(league_id="L1", name="League", season=2026, roster_positions=positions, scoring_settings=scoring)
    roster = {"owner_id": "U1", "roster_id": "R1", "players": list(players), "starters": list(starters), "metadata": {"team_name": "Team"}}
    return build_snapshot(roster, league, mappings)


def test_snapshot_hash_ignores_api_ordering():
    first = snapshot(players=("1", "2", "3"), starters=("1", "2"))
    second = snapshot(players=("3", "1", "2"), starters=("2", "1"))
    assert snapshot_hash(first) == snapshot_hash(second)


def test_repeated_identical_sync_has_no_source_changes():
    previous, latest = snapshot(), snapshot()
    diff = detect_changes(previous, latest, {"gsis-1", "gsis-2"})
    assert not diff.has_changes
    assert not diff.local_lineup_conflict


def test_roster_refresh_is_separate_from_lineup_change():
    previous = snapshot(players=("1", "2", "3"), starters=("1", "2"))
    latest = snapshot(players=("1", "2", "4"), starters=("1", "2"))
    diff = detect_changes(previous, latest, {"gsis-1", "gsis-2"})
    assert diff.roster_changed
    assert diff.roster_added == ("4",)
    assert diff.roster_removed == ("3",)
    assert not diff.lineup_changed


def test_lineup_change_is_detected_without_roster_change():
    previous = snapshot(starters=("1", "2"))
    latest = snapshot(starters=("1", "3"))
    diff = detect_changes(previous, latest, {"gsis-1", "gsis-2"})
    assert not diff.roster_changed
    assert diff.lineup_changed
    assert diff.starters_added == ("3",)
    assert diff.starters_removed == ("2",)
    assert diff.local_lineup_conflict


def test_local_sdl_lineup_divergence_does_not_become_source_change():
    previous, latest = snapshot(), snapshot()
    diff = detect_changes(previous, latest, {"gsis-1", "gsis-3"})
    assert not diff.has_changes
    assert diff.local_lineup_conflict


def test_scoring_and_roster_configuration_changes_are_explicit():
    previous = snapshot()
    latest = snapshot(positions=("QB", "RB", "FLEX", "BN"), scoring={"pass_td": 6, "rec": 1})
    diff = detect_changes(previous, latest)
    assert set(diff.league_changes) == {"roster_positions", "scoring_settings"}


def test_unmatched_player_is_preserved_and_forces_review():
    latest = snapshot(players=("1", "99"), starters=("1",), unmatched=("99",))
    diff = detect_changes(snapshot(players=("1",), starters=("1",)), latest)
    assert diff.unmatched == ("99",)
    assert diff.has_changes
    assert latest["unmatched"][0]["external_player_id"] == "99"
