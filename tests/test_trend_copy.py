import ast
from pathlib import Path

import pytest

from dashboard.trend_copy import context_age_copy, sustainability_label, workload_label


@pytest.mark.parametrize("values", [[], [3], [3, 12], [3, 12, 9], [2, None, 5, 9]])
def test_sustainability_respects_role_evidence(values):
    role = workload_label(values, "targets")[0]
    title, copy, style = sustainability_label(role, 10, 5, 20)
    assert title == "Sustainability unclear"
    assert style == ""
    assert "established" not in copy


@pytest.mark.parametrize("production,tds,opportunity,title", [
    (3, 2, 1, "Scoring is touchdown-led"),
    (3, 2, 1.5, "Production has volume support"),
    (0, 0, 0, "No clear volume-led increase"),
    (-3, 0, -2, "No clear volume-led increase"),
    (float("nan"), 2, 3, "Sustainability unclear"),
    (3, None, 3, "Sustainability unclear"),
])
def test_sustainability_complete_samples_and_invalid_metrics(production, tds, opportunity, title):
    assert sustainability_label("Role is holding steady", production, tds, opportunity)[0] == title


@pytest.mark.parametrize("values", [[], [3], [3, 12], [3, 12, 9]])
def test_short_samples_do_not_claim_established_role(values):
    assert workload_label(values, "targets")[0] == "Early role sample"


@pytest.mark.parametrize("values,title", [
    ([1, 1, 10, 10, 10], "Opportunity is growing"),
    ([10, 10, 1, 1, 1], "Opportunity is shrinking"),
    ([5, 5, 5, 5], "Role is holding steady"),
])
def test_existing_threshold_and_window(values, title):
    before = list(values)
    label, copy, _ = workload_label(values, "targets")
    assert label == title
    assert "Last 3 recorded games" in copy
    assert values == before


@pytest.mark.parametrize("value", [None, float("nan"), -1, "missing"])
def test_missing_workload(value):
    assert workload_label([2, 3, value, 4], "targets")[0] == "Workload data incomplete"


@pytest.mark.parametrize("age", [None, float("nan"), float("inf"), -1, "missing"])
def test_unknown_age_never_looks_fresh(age):
    assert context_age_copy(age, True) == "Retrieval time unavailable; report freshness unverified"


def test_retrieval_is_distinct_from_report_freshness():
    assert context_age_copy(0) == "Retrieved 0 min ago; report freshness unverified"
    assert context_age_copy(12, True) == "Retrieved 12 min ago; report freshness verified"


def test_app_reuses_summary_copy_without_second_role_calculation():
    source = (Path(__file__).parents[1] / "dashboard/app.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "change_copy = role_title" in source
    assert "html.escape(role_copy)" in source
    assert "comparison_opportunity =" not in source
    assert "live context {context_age_minutes}m ago" not in source
    assert "{context_age_minutes}m ago" not in source
    assert "sustainability_label(\n        role_title," in source
    assert "Production near established role" not in source


def test_monitoring_copy_does_not_promise_unverified_scheduled_execution():
    source = (Path(__file__).parents[1] / "dashboard/app.py").read_text(encoding="utf-8")
    assert 'next_refresh_copy = "Next publication time not confirmed"' in source
    assert "<b>Publication schedule</b>" in source
    assert "high_frequency_day" not in source
    assert "6 AM / 5 PM Central" not in source
    assert "Game-window monitoring" not in source
