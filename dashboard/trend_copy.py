"""Presentation-only workload and source-age wording; never changes projections."""

import math


def workload_label(values, opportunity_name):
    """Use last three recorded games versus season, with explicit sample limits."""
    sample = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "Workload data incomplete", "Missing workload data prevents a reliable role trend.", ""
        if not math.isfinite(number) or number < 0:
            return "Workload data incomplete", "Missing workload data prevents a reliable role trend.", ""
        sample.append(number)
    if len(sample) < 4:
        return (
            "Early role sample",
            f"Only {len(sample)} recorded games; the recent three-game window does not yet have a separate earlier baseline. A single-week change is not an established role trend.",
            "",
        )
    change = sum(sample[-3:]) / 3 - sum(sample) / len(sample)
    window = f"Last 3 recorded games versus all {len(sample)} season games"
    if change >= 1.5:
        return "Opportunity is growing", f"{window}: {opportunity_name} are {change:.1f} per game higher.", "positive"
    if change <= -1.5:
        return "Opportunity is shrinking", f"{window}: {opportunity_name} are {abs(change):.1f} per game lower.", "negative"
    return "Role is holding steady", f"{window}: {opportunity_name} remain close to the season rate.", ""


def sustainability_label(role_title, production_delta, recent_touchdowns, opportunity_delta):
    """Presentation only: respect the role card's sample and data limitations."""
    if role_title == "Workload data incomplete":
        return "Sustainability unclear", "Workload data is incomplete; volume support cannot be assessed reliably.", ""
    if role_title == "Early role sample":
        return "Sustainability unclear", "The role sample is too short to assess whether recent production is supported by sustained workload.", ""
    try:
        metrics = tuple(float(value) for value in (production_delta, recent_touchdowns, opportunity_delta))
    except (TypeError, ValueError):
        metrics = ()
    if len(metrics) != 3 or not all(math.isfinite(value) for value in metrics):
        return "Sustainability unclear", "Production data is incomplete; scoring sustainability cannot be assessed reliably.", ""
    production_delta, recent_touchdowns, opportunity_delta = metrics
    if production_delta > 2 and recent_touchdowns >= 2 and opportunity_delta < 1.5:
        return "Scoring is touchdown-led", f"{recent_touchdowns:.0f} touchdowns in the recent sample are lifting results without the same increase in workload.", "negative"
    if opportunity_delta >= 1.5:
        return "Production has volume support", "The recent scoring change is accompanied by a meaningful workload increase.", "positive"
    return "No clear volume-led increase", "The recent workload window does not show a meaningful increase over the season rate; this does not establish that scoring will repeat.", ""


def context_age_copy(age_minutes, source_verified=False):
    """Retrieval recency is not proof of official report freshness."""
    try:
        age = float(age_minutes)
    except (TypeError, ValueError):
        age = float("nan")
    if not math.isfinite(age) or age < 0:
        return "Retrieval time unavailable; report freshness unverified"
    return f"Retrieved {int(age)} min ago; report freshness {'verified' if source_verified else 'unverified'}"
