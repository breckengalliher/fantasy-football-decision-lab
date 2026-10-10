"""Public product landing and lightweight mobile navigation."""

from __future__ import annotations

import html
import os
from urllib.parse import urlencode
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.presentation import player_photo_html
from dashboard.trust_layer import render_trust_strip


def _route(view: str, **params: str) -> None:
    st.query_params.clear()
    st.query_params["view"] = view
    for key, value in params.items():
        st.query_params[key] = value
    st.rerun()


def mobile_navigation() -> None:
    context = {key: str(st.query_params[key]) for key in ("team", "qb") if key in st.query_params}
    def link(view):
        return html.escape("?" + urlencode({"view": view, **context}), quote=True)
    extra_links = f'<a href="{link("player-trends")}" target="_self"><b>↗</b><span>Trends</span></a>'
    if os.environ.get('SDL_RESTRICTED_PILOT') != '1':
        extra_links += (
        f'<a href="{link("how-it-works")}" target="_self"><b>ⓘ</b><span>Method</span></a>'
        )
    st.markdown(
        '<nav class="mobile-nav" aria-label="Primary">'
        f'<a href="{link("command-center")}" target="_self"><b>⌂</b><span>Command</span></a>'
        f'<a href="{link("decision-room")}" target="_self"><b>⇄</b><span>Compare</span></a>'
        f'{extra_links}'
        '</nav>', unsafe_allow_html=True,
    )


def render_home(board: pd.DataFrame, metadata: dict[str, Any], season: int) -> None:
    st.markdown(
        '<section class="landing-hero"><div><span>THE SUNDAY DECISION LAB</span>'
        '<h1>Make the lineup call<br><em>before kickoff.</em></h1>'
        '<p>A focused fantasy football decision tool that turns projections, availability, workload, and matchup context into a clear next action.</p></div>'
        '<aside><b>ANSWER FIRST</b><strong>Start / Sit</strong><span>Supporting evidence stays one tap away.</span></aside></section>',
        unsafe_allow_html=True,
    )
    primary, secondary = st.columns(2)
    if primary.button("Try a sample decision", type="primary", width="stretch"):
        names = [str(value) for value in board.loc[(board["position"] == "WR") & board["is_roster_relevant"], "player"].head(2)]
        _route("decision-room", position="WR", players="|".join(names), qb="4")
    if secondary.button("Connect my fantasy team", width="stretch"):
        _route("command-center")
    st.caption("No account is required to compare players. Sign in only when you want to save and monitor a roster.")
    render_trust_strip(metadata, compact=False)

    eligible = board.loc[board["is_roster_relevant"] & board["next_opponent"].notna()].sort_values("median_ppr", ascending=False)
    featured = eligible.drop_duplicates("position").head(3)
    st.markdown('<div class="landing-section"><span>LIVE PRODUCT PREVIEW</span><h2>See the decision, then inspect the why</h2></div>', unsafe_allow_html=True)
    columns = st.columns(max(1, len(featured)))
    for column, (_, row) in zip(columns, featured.iterrows()):
        with column:
            photo = player_photo_html(row.get("headshot_url"), row["player"])
            st.markdown(
                f'<article class="landing-player"><div class="landing-player-identity">{photo}<div><span>{html.escape(str(row["position"]))} · {html.escape(str(row["team"]))} vs {html.escape(str(row["next_opponent"]))}</span>'
                f'<h3>{html.escape(str(row["player"]))}</h3></div></div><strong>{float(row["median_ppr"]):.1f}<small> PPR</small></strong>'
                f'<p>{float(row["floor_ppr"]):.1f}–{float(row["ceiling_ppr"]):.1f} projection range</p></article>', unsafe_allow_html=True,
            )
    st.markdown(
        '<section class="landing-steps"><div><b>1</b><strong>Compare</strong><span>Search any supported QB, RB, WR, or TE.</span></div>'
        '<div><b>2</b><strong>Understand</strong><span>See the edge, uncertainty, injury context, usage, and matchup.</span></div>'
        '<div><b>3</b><strong>Monitor</strong><span>Save a roster and return Sunday for an action-first safety check.</span></div></section>',
        unsafe_allow_html=True,
    )
    st.info("The model supports Full PPR with 4- or 6-point passing touchdowns. Projection differences under 2 PPR are treated as close calls, not strong edges.")
