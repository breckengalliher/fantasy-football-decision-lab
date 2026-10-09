"""Evidence-backed trust copy for projections and freshness."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st


REPORT = Path(__file__).resolve().parents[1] / "reports" / "model-validation-audit" / "model-validation-audit.json"


@st.cache_data(show_spinner=False)
def validation_summary() -> dict[str, Any]:
    try:
        audit = json.loads(REPORT.read_text(encoding="utf-8"))
        metrics = audit["benchmarks_2025"]["incumbent"]
        interval = audit["production_interval_audit"]
        return {
            "samples": int(metrics["point_accuracy"]["samples"]),
            "mae": float(metrics["point_accuracy"]["mae"]),
            "ordering": float(metrics["start_sit"]["accuracy"]),
            "coverage": float(interval["coverage"]),
            "study": str(audit["study_classification"]),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def ordering_label(metrics: dict[str, Any]) -> str:
    """Missing evidence must never be presented as measured zero accuracy."""
    value = metrics.get("ordering")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "Unavailable · validation report not loaded"
    if not math.isfinite(value) or not 0 <= value <= 1:
        return "Unavailable · validation report not loaded"
    return f"{value:.1%} in 2025"


def render_trust_strip(metadata: dict[str, Any], *, compact: bool = True) -> None:
    refreshed = str(metadata.get("refreshed_at") or "Unavailable")
    context = str(metadata.get("context_refreshed_at") or metadata.get("sportsdataio_refreshed_at") or "Unavailable")
    def age(value: str) -> str:
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            minutes = max(0, int((datetime.now(timezone.utc) - stamp).total_seconds() // 60))
            return f"{minutes}m ago"
        except ValueError:
            return "unavailable"
    metrics = validation_summary()
    st.markdown(
        '<div class="trust-strip">'
        f'<span><b>Projection snapshot</b>{age(refreshed)}</span>'
        f'<span><b>Context retrieved</b>{age(context)}</span>'
        f'<span><b>Injury/depth report freshness</b>{"Verified" if metadata.get("injury_freshness_verified") is True and metadata.get("depth_freshness_verified") is True else "Unverified · check official reports"}</span>'
        '<span><b>Model status</b>Production · monitored</span>'
        f'<span><b>Validated ordering</b>{ordering_label(metrics)}</span>'
        '</div>', unsafe_allow_html=True,
    )
    if not compact:
        with st.expander("How reliable are these projections?"):
            if metrics:
                st.write(f"On a 3,170 player-week 2025 walk-forward test, mean absolute error was {metrics['mae']:.2f} PPR and ordering accuracy was {metrics['ordering']:.1%}. The production P10–P90 range covered {metrics['coverage']:.1%} of outcomes.")
                st.caption("This is a walk-forward box-score simulation, not an archive of exact forecasts previously shown to users. Differences under 2 PPR remain close calls.")
            else:
                st.info("The local validation report is unavailable. No accuracy claim is being shown.")
