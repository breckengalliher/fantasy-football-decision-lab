"""Shared decision-language thresholds for projections and UI surfaces."""

CLOSE_CALL_THRESHOLD_PPR = 2.0
MODERATE_EDGE_THRESHOLD_PPR = 5.0


def is_close_call(gap: float) -> bool:
    return float(gap) < CLOSE_CALL_THRESHOLD_PPR


def edge_label(gap: float) -> str:
    value = float(gap)
    if value < CLOSE_CALL_THRESHOLD_PPR:
        return "Close call"
    if value < MODERATE_EDGE_THRESHOLD_PPR:
        return "Moderate edge"
    return "Strong edge"
