from dashboard.states import empty_player_pool_message, provider_issue_message


def test_provider_states_preserve_core_projection_availability():
    assert provider_issue_message("Connected · now") is None
    assert "Core projections are still available" in provider_issue_message("Connection error · TimeoutError")
    assert "official inactive" in provider_issue_message("Not connected")


def test_empty_qb_pool_explains_verified_starter_gate():
    message = empty_player_pool_message("QB", hidden_qbs=4)
    assert "No verified QB1" in message
    assert "4 relevant QB record(s)" in message


def test_empty_skill_pool_suggests_next_action():
    message = empty_player_pool_message("TE")
    assert "No eligible TE" in message
    assert "refresh" in message.lower()
