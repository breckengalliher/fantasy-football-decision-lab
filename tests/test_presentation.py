import pandas as pd

from dashboard.presentation import comparison_summary, matchup_summary, role_summary, weather_summary


def test_context_summaries_are_brief_and_explanatory():
    row = {
        "schedule_adjusted_index": .8,
        "latest_snap_pct": .86,
        "recent_snap_pct": .81,
        "weather_summary_live": "Clear Sky",
        "temperature_live": 88,
        "wind_live": 3,
    }
    assert matchup_summary(row) == "20% tougher than baseline"
    assert role_summary(row) == "86% snaps · role expanding"
    assert weather_summary(row) == "Clear Sky · 88°F · calm wind"


def test_comparison_summary_calls_out_a_toss_up():
    frame = pd.DataFrame([
        {"player": "JSN", "median_ppr": 21.6},
        {"player": "Lamb", "median_ppr": 21.3},
    ])
    assert comparison_summary(frame) == "JSN is the preferred start, 0.3 PPR ahead of Lamb. This is a genuine toss-up."
