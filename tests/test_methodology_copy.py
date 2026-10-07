from dashboard.methodology_copy import DISCLAIMER_LANGUAGE, METHODOLOGY_LANGUAGE, SOURCE_ATTRIBUTION


def test_sources_distinguish_provider_data_from_app_outputs():
    assert "nflverse" in SOURCE_ATTRIBUTION
    assert "SportsDataIO" in SOURCE_ATTRIBUTION
    assert "produced by this app" in SOURCE_ATTRIBUTION
    assert "never silently interpreted as healthy" in SOURCE_ATTRIBUTION


def test_methodology_preserves_context_separation_and_relative_verdict():
    assert "only the players selected" in METHODOLOGY_LANGUAGE
    assert "Decision Context only" in METHODOLOGY_LANGUAGE
    assert "do not alter the Start/Sit ranking" in METHODOLOGY_LANGUAGE
    assert "P10, median and P90" in METHODOLOGY_LANGUAGE
    assert "narrative only" in METHODOLOGY_LANGUAGE
    assert "never change the projection" in METHODOLOGY_LANGUAGE


def test_disclaimer_covers_freshness_and_final_responsibility():
    assert "feeds can be delayed" in DISCLAIMER_LANGUAGE
    assert "before kickoff" in DISCLAIMER_LANGUAGE
    assert "final lineup decision" in DISCLAIMER_LANGUAGE
