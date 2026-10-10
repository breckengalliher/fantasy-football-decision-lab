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


def test_fresh_retrieval_without_official_verification_discloses_missing_report(monkeypatch):
    from dashboard import trust_layer
    captions = []
    monkeypatch.setattr(trust_layer.st, 'markdown', lambda *args, **kwargs: None)
    monkeypatch.setattr(trust_layer.st, 'caption', captions.append)
    monkeypatch.setattr(trust_layer, 'validation_summary', lambda: {})
    trust_layer.render_trust_strip({'context_refreshed_at': '2026-10-10T20:00:00Z',
                                  'injury_freshness_verified': False,
                                  'depth_freshness_verified': False})
    assert captions == ['Last verified official injury/depth report: unavailable. Context retrieval time is not official report time.']
