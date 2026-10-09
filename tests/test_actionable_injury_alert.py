from dashboard.presentation import actionable_injury_alert


def test_confirmed_unavailable_is_highest_priority():
    alert = actionable_injury_alert({
        "injury_status_live": "Out",
        "practice_status_live": "DNP",
        "injury_updated_live": "2026-10-07T18:30:00Z",
    })
    assert alert["classification"] == "Confirmed unavailable"
    assert alert["level"] == "unavailable"
    assert "Changed Oct 7" in alert["changed"]
    assert "inactive list" in alert["verify"]


def test_questionable_limited_requires_lineup_action():
    alert = actionable_injury_alert({
        "injury_status_live": "Questionable",
        "practice_status_live": "Limited Participation in Practice",
        "injury_updated_live": 1791397259531,
    })
    assert alert["classification"] == "Lineup action may be needed"
    assert "final practice designation" in alert["verify"]


def test_questionable_without_practice_detail_is_monitor():
    alert = actionable_injury_alert({"injury_status_live": "Questionable"})
    assert alert["classification"] == "Monitor"
    assert alert["changed"] == "Status change time unavailable"


def test_healthy_teammate_boost_is_opportunity_alert():
    alert = actionable_injury_alert({
        "injury_teammate_boost": 1.4,
        "injury_teammate_effect": "Starting running back reduced availability could create additional opportunity.",
        "injury_checked_at": "2026-10-07T12:00:00Z",
    })
    assert alert["classification"] == "Teammate opportunity increase"
    assert alert["level"] == "opportunity"
    assert alert["changed"].startswith("Change time unavailable · checked")


def test_healthy_player_stays_visually_quiet():
    assert actionable_injury_alert({}) is None
