from dashboard.decision_policy import CLOSE_CALL_THRESHOLD_PPR, edge_label, is_close_call


def test_sub_two_point_gap_is_never_a_strong_edge():
    assert CLOSE_CALL_THRESHOLD_PPR == 2.0
    assert is_close_call(1.99)
    assert edge_label(1.99) == "Close call"


def test_larger_gaps_have_separate_labels():
    assert edge_label(2.0) == "Moderate edge"
    assert edge_label(5.0) == "Strong edge"
