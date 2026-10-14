import pandas as pd

from src.sunday_status_alerts import meaningful_status_changes


def test_alerts_on_real_status_semantics_only():
    old = pd.DataFrame([
        {"gsis_id": "1", "team": "SEA", "full_name": "Alpha", "report_status": None, "practice_status": "Limited Participation in Practice"},
        {"gsis_id": "2", "team": "DAL", "full_name": "Bravo", "report_status": None, "practice_status": "Did Not Participate In Practice"},
    ])
    new = pd.DataFrame([
        {"gsis_id": "1", "team": "SEA", "full_name": "Alpha", "report_status": "Questionable", "practice_status": "Did Not Participate In Practice"},
        {"gsis_id": "2", "team": "DAL", "full_name": "Bravo", "report_status": None, "practice_status": "Limited Participation in Practice"},
    ])

    alerts = meaningful_status_changes(old, new)
    assert len(alerts) == 1
    assert alerts[0]["player"] == "Alpha"
    assert alerts[0]["reason"] == "report status change"
