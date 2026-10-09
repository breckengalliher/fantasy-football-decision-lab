import pytest

from dashboard.trust_layer import ordering_label


@pytest.mark.parametrize("metrics", [{}, {"ordering": None}, {"ordering": "0.9"},
                                      {"ordering": float("nan")}, {"ordering": float("inf")},
                                      {"ordering": -0.1}, {"ordering": 1.1}, {"ordering": True}])
def test_missing_or_invalid_evidence_is_not_reported_as_zero(metrics):
    assert ordering_label(metrics) == "Unavailable · validation report not loaded"


def test_verified_zero_remains_zero():
    assert ordering_label({"ordering": 0.0}) == "0.0% in 2025"


def test_verified_ordering_is_preserved():
    assert ordering_label({"ordering": 0.743}) == "74.3% in 2025"
