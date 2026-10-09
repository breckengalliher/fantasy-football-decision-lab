import pandas as pd

from src.qb_scoring_format_evaluation import add_qb_scoring


def test_six_point_format_adds_two_points_per_passing_td():
    frame = pd.DataFrame([{
        "fantasy_points_ppr": 20.0, "passing_tds": 3,
        "passing_interceptions": 1, "fumbles_lost_total": 0,
    }])
    four = add_qb_scoring(frame, 4)
    six = add_qb_scoring(frame, 6)
    assert four.loc[0, "qb_points"] == 20.0
    assert six.loc[0, "qb_points"] == 26.0
    assert six.loc[0, "turnovers"] == 1
