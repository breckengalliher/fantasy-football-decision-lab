"""Fantasy Football Decision Lab — Streamlit dashboard scaffold."""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.data import (
    apply_market_values,
    load_dashboard_players,
    player_history,
    prepare_draft_board,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEAGUE_CONFIG = json.loads((PROJECT_ROOT / "config" / "league.json").read_text())
PLAYERS, DATA_STATUS = load_dashboard_players()

st.set_page_config(
    page_title="Fantasy Football Decision Lab",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    :root {
        --ink: #14212b;
        --muted: #5d6b78;
        --navy: #17324d;
        --blue: #2468a2;
        --gold: #d39a2c;
        --paper: #f5f7f9;
        --line: #dce3e8;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stSidebar"] { background: #10283d; }
    [data-testid="stSidebar"] * { color: #f5f8fa; }
    .hero {
        padding: 1.5rem 1.65rem;
        border-radius: 18px;
        background: linear-gradient(125deg, #10283d 0%, #1d5379 72%, #d39a2c 150%);
        color: white;
        margin-bottom: 1rem;
        box-shadow: 0 12px 30px rgba(20,33,43,.12);
    }
    .hero h1 { margin: 0; font-size: 2.15rem; letter-spacing: -.03em; }
    .hero p { margin: .45rem 0 0; color: #dce7ef; max-width: 800px; }
    .status {
        display: inline-block;
        padding: .28rem .62rem;
        border-radius: 999px;
        background: #fff3d2;
        color: #7a5310;
        font-size: .78rem;
        font-weight: 700;
        margin-bottom: .65rem;
    }
    .section-title { margin: 1.1rem 0 .35rem; font-weight: 750; font-size: 1.25rem; }
    .section-copy { color: var(--muted); margin-bottom: .9rem; }
    .rank-row {
        display: grid;
        grid-template-columns: 170px 1fr 60px;
        align-items: center;
        gap: .7rem;
        margin: .5rem 0;
    }
    .rank-track { height: 12px; border-radius: 99px; background: #e4e9ed; overflow: hidden; }
    .rank-fill { height: 100%; border-radius: 99px; background: #2468a2; }
    .rank-fill.gold { background: #d39a2c; }
    .signal {
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: .85rem 1rem;
        background: white;
        min-height: 98px;
    }
    .signal strong { font-size: 1.25rem; }
    .muted { color: var(--muted); }
    .source-note {
        margin-top: 1rem;
        padding: .75rem 1rem;
        background: #eef3f6;
        border-left: 4px solid #2468a2;
        color: #42515e;
        font-size: .88rem;
    }
    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid var(--line);
        padding: .75rem 1rem;
        border-radius: 14px;
    }
</style>
""",
    unsafe_allow_html=True,
)


def metric_bar(label: str, value: float, maximum: float, gold: bool = False) -> str:
    width = max(0.0, min(100.0, 100 * value / maximum))
    fill_class = "rank-fill gold" if gold else "rank-fill"
    return (
        '<div class="rank-row">'
        f"<span>{html.escape(label)}</span>"
        f'<div class="rank-track"><div class="{fill_class}" style="width:{width:.1f}%"></div></div>'
        f"<strong>{value:.1f}</strong>"
        "</div>"
    )


with st.sidebar:
    st.title("Decision Lab")
    st.caption("2026 draft decision application")
    workspace = st.radio(
        "Workspace",
        [
            "Overview",
            "Draft Target Finder",
            "Weekly Start / Sit",
            "Player Explorer",
            "Methodology",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.subheader("League profile")
    st.write("12 teams · Full PPR · $200 auction")
    st.write("6-point passing TDs")
    st.write("1 QB · 2 RB · 2 WR · 1 TE · 2 FLEX")
    st.write("1 DST · 6 bench · No kicker")
    st.divider()
    st.caption("DATA STATUS")
    if DATA_STATUS.startswith("Historical model"):
        st.success("2026 roster + model connected")
        st.caption("2023–2025 nflverse results, weighted toward 2025.")
        if "market matches" in DATA_STATUS:
            st.caption(DATA_STATUS.split(" + ", 1)[1].capitalize() + ".")
    else:
        st.warning("Illustrative fallback", icon="⚠️")
        st.caption("Run the pipeline to connect historical player results.")
    st.divider()
    st.caption("OPTIONAL MARKET DATA")
    market_upload = st.file_uploader(
        "Import reviewed auction values",
        type=["csv"],
        help="CSV columns required: player, market_value, season. Season must be 2026.",
    )
    if market_upload is not None:
        try:
            PLAYERS, matched_players = apply_market_values(
                PLAYERS, pd.read_csv(market_upload)
            )
            st.success(f"Matched {matched_players} market values")
        except (ValueError, pd.errors.ParserError) as error:
            st.error(str(error))

st.markdown(
    """
<div class="hero">
    <span class="status">HISTORICAL MODEL</span>
    <h1>Fantasy Football Decision Lab</h1>
    <p>Turn custom league scoring, opportunity, replacement value, and matchup context into
    clearer auction and weekly lineup decisions.</p>
</div>
""",
    unsafe_allow_html=True,
)

draft_board = prepare_draft_board(PLAYERS)
has_uploaded_market = draft_board["comparison_source"].eq(
    "Uploaded 2026 market file"
).any()
has_espn_market = draft_board["comparison_source"].str.startswith(
    "ESPN PPR calibrated", na=False
).any()
comparison_name = (
    "uploaded market"
    if has_uploaded_market
    else "ESPN 12-team PPR value"
    if has_espn_market
    else "2025 baseline"
)

if workspace == "Overview":
    value_targets = draft_board.loc[draft_board["auction_edge"].gt(3)].copy()
    top_value = draft_board.iloc[0]
    safest_player = PLAYERS.loc[PLAYERS["projected_points"].notna()].sort_values(
        ["risk_score", "projected_points"], ascending=[True, False]
    ).iloc[0]
    risk_watch = PLAYERS.loc[PLAYERS["projected_points"].notna()].sort_values(
        ["risk_score", "model_value"], ascending=[False, False]
    ).iloc[0]

    st.markdown('<div class="section-title">2026 decision snapshot</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">Start with the highest-signal decisions, then open a workspace for deeper analysis.</div>',
        unsafe_allow_html=True,
    )

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Draft targets", len(value_targets))
    metric_two.metric("Largest value difference", f"+${int(top_value['auction_edge'])}")
    metric_three.metric("Allocated league budget", f"${int(draft_board['model_value'].sum()):,}")
    metric_four.metric("Data status", DATA_STATUS)

    st.subheader("Today’s decision board")
    insight_one, insight_two, insight_three = st.columns(3)
    with insight_one:
        st.markdown(
            f"""
            <div class="signal">
                <span class="muted">BEST VALUE</span><br/>
                <strong>{html.escape(top_value["player"])}</strong><br/>
                ${top_value["model_value"]} league value · ${top_value["market_value"]} {comparison_name} ·
                <b>+${top_value["auction_edge"]}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with insight_two:
        st.markdown(
            f"""
            <div class="signal">
                <span class="muted">STRONGEST FLOOR PROFILE</span><br/>
                <strong>{html.escape(safest_player["player"])}</strong><br/>
                {safest_player["floor"]:.0f}-point floor · {safest_player["confidence"]} confidence ·
                {safest_player["risk_score"]}/100 risk
            </div>
            """,
            unsafe_allow_html=True,
        )
    with insight_three:
        st.markdown(
            f"""
            <div class="signal">
                <span class="muted">RISK WATCH</span><br/>
                <strong>{html.escape(risk_watch["player"])}</strong><br/>
                {risk_watch["risk_score"]}/100 risk · ${risk_watch["model_value"]} league value ·
                {risk_watch["confidence"]} confidence
            </div>
            """,
            unsafe_allow_html=True,
        )

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader(f"Top differences vs {comparison_name}")
        edge_rows = draft_board.loc[draft_board["auction_edge"].gt(0)].head(6)
        edge_html = "".join(
            metric_bar(
                f"{row.player} · {row.position}",
                float(row.auction_edge),
                max(float(edge_rows["auction_edge"].max()), 1),
                gold=index == 0,
            )
            for index, row in enumerate(edge_rows.itertuples())
        )
        st.markdown(edge_html, unsafe_allow_html=True)
        st.caption(
            "Custom league value minus the displayed comparison. Uploaded 2026 "
            "market data is optional and never determines the league value."
        )
    with right:
        st.subheader("Value by position")
        position_summary = (
            draft_board.groupby("position", as_index=False)
            .agg(
                average_edge=("auction_edge", "mean"),
                top_edge=("auction_edge", "max"),
                players=("player", "count"),
            )
            .sort_values("average_edge", ascending=False)
        )
        position_html = "".join(
            metric_bar(
                row.position,
                float(max(row.average_edge, 0)),
                max(float(position_summary["average_edge"].clip(lower=0).max()), 1),
                gold=index == 0,
            )
            for index, row in enumerate(position_summary.itertuples())
        )
        st.markdown(position_html, unsafe_allow_html=True)
        st.caption("Average model-versus-baseline edge by position.")

    st.subheader("Open a workspace")
    action_one, action_two, action_three = st.columns(3)
    action_one.info(
        "**Draft Target Finder**\n\nFilter the auction board and identify price-sensitive targets."
    )
    action_two.info(
        "**Weekly Start / Sit**\n\nCompare projected output, matchup, floor, ceiling, and risk."
    )
    action_three.info(
        "**Player Explorer**\n\nInspect the advanced statistics behind each recommendation."
    )

    st.subheader("Highest-priority targets")
    st.dataframe(
        value_targets[
            [
                "player",
                "position",
                "team",
                "model_value",
                "market_value",
                "auction_edge",
                "projected_points",
                "confidence",
            ]
        ].head(5),
        hide_index=True,
        width="stretch",
    )

elif workspace == "Draft Target Finder":
    st.markdown('<div class="section-title">Build an auction shortlist</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="section-copy">Rank custom league values and compare them with the {comparison_name}.</div>',
        unsafe_allow_html=True,
    )

    filter_one, filter_two, filter_three = st.columns([1.4, 1, 1])
    with filter_one:
        selected_positions = st.multiselect(
            "Positions",
            ["QB", "RB", "WR", "TE", "DST"],
            default=["QB", "RB", "WR", "TE", "DST"],
        )
    with filter_two:
        maximum_price = st.slider(f"Maximum {comparison_name} value", 0, 70, 70)
    with filter_three:
        minimum_edge = st.slider("Minimum value difference", -10, 15, 0)

    filtered = draft_board.loc[
        draft_board["position"].isin(selected_positions)
        & draft_board["market_value"].le(maximum_price)
        & draft_board["auction_edge"].ge(minimum_edge)
    ].copy()

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("League budget", "$2,400")
    metric_two.metric("Allocated budget", f"${int(draft_board['model_value'].sum()):,}")
    metric_three.metric("Targets found", f"{len(filtered)}")
    metric_four.metric(
        "Best value difference",
        f"${int(filtered['auction_edge'].max())}" if not filtered.empty else "—",
    )

    left, right = st.columns([1.1, 1])
    with left:
        st.subheader(f"Highest differences vs {comparison_name}")
        if filtered.empty:
            st.info("No players match the current filters.")
        else:
            bars = "".join(
                metric_bar(
                    f"{row.player} · {row.position}",
                    float(max(row.auction_edge, 0)),
                    max(float(filtered["auction_edge"].max()), 1),
                    gold=index == 0,
                )
                for index, row in enumerate(filtered.head(6).itertuples())
            )
            st.markdown(bars, unsafe_allow_html=True)
    with right:
        st.subheader("Draft signal")
        if filtered.empty:
            st.info("Broaden the filters to see a recommendation.")
        else:
            leader = filtered.iloc[0]
            st.markdown(
                f"""
                <div class="signal">
                    <span class="muted">Top model target</span><br/>
                    <strong>{html.escape(leader["player"])}</strong><br/>
                    League ${leader["model_value"]} · Comparison ${leader["market_value"]} ·
                    <b>+${leader["auction_edge"]} edge</b>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(
                "Why: favorable value-over-replacement profile, opportunity score, "
                "and comparison difference. The league value is calculated independently."
            )

    st.subheader("Auction board")
    display_columns = [
        "player",
        "position",
        "team",
        "projected_points",
        "floor",
        "ceiling",
        "model_value",
        "market_value",
        "auction_edge",
        "comparison_source",
        "value_signal",
        "confidence",
        "roster_status",
        "depth_label",
    ]
    st.dataframe(
        filtered[display_columns],
        hide_index=True,
        width="stretch",
        column_config={
            "player": "Player",
            "position": "Pos",
            "team": "Team",
            "projected_points": st.column_config.NumberColumn("Proj. PPR", format="%.1f"),
            "model_value": st.column_config.NumberColumn("League $", format="$%d"),
            "market_value": st.column_config.NumberColumn("Comparison $", format="$%.2f"),
            "auction_edge": st.column_config.NumberColumn("Difference", format="$%d"),
        },
    )

elif workspace == "Weekly Start / Sit":
    st.markdown('<div class="section-title">Compare weekly lineup options</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">Balance median projection, floor, ceiling, matchup, and confidence.</div>',
        unsafe_allow_html=True,
    )
    st.warning(
        "Injury availability is not included in these recommendations. "
        "Confirm current team reports before setting a lineup.",
        icon="⚠️",
    )
    eligible_names = PLAYERS.loc[
        PLAYERS["position"].ne("DST") & PLAYERS["weekly_projection"].notna(), "player"
    ].tolist()
    selected_names = st.multiselect(
        "Players to compare",
        eligible_names,
        default=eligible_names[:3],
        max_selections=4,
    )
    comparison = PLAYERS.loc[PLAYERS["player"].isin(selected_names)].copy()

    if comparison.empty:
        st.info("Select at least one player.")
    else:
        recommended = comparison.sort_values(
            ["weekly_projection", "risk_score"], ascending=[False, True]
        ).iloc[0]
        metric_one, metric_two, metric_three = st.columns(3)
        metric_one.metric("Recommended start", recommended["player"])
        metric_two.metric("Projected PPR", f"{recommended['weekly_projection']:.1f}")
        metric_three.metric("Matchup", recommended["matchup"])

        left, right = st.columns([1.1, 1])
        with left:
            st.subheader("Weekly projection")
            bars = "".join(
                metric_bar(
                    f"{row.player} · vs {row.opponent}",
                    float(row.weekly_projection),
                    max(float(comparison["weekly_projection"].max()), 1),
                    gold=row.player == recommended["player"],
                )
                for row in comparison.sort_values("weekly_projection", ascending=False).itertuples()
            )
            st.markdown(bars, unsafe_allow_html=True)
        with right:
            st.subheader("Decision context")
            st.write(
                f"**{recommended['player']}** leads the demo comparison because the "
                f"{recommended['weekly_projection']:.1f}-point median projection is paired "
                f"with a {recommended['matchup'].lower()} matchup and "
                f"{recommended['confidence'].lower()} confidence."
            )
            st.caption(
                "Injury status is unavailable because no reviewed 2026 feed is connected. "
                "Confidence reflects model coverage and role stability, not health."
            )

        st.dataframe(
            comparison[
                [
                    "player",
                    "position",
                    "team",
                    "opponent",
                    "weekly_projection",
                    "floor",
                    "ceiling",
                    "matchup",
                    "confidence",
                    "risk_score",
                    "injury_status",
                    "depth_label",
                ]
            ].sort_values("weekly_projection", ascending=False),
            hide_index=True,
            width="stretch",
            column_config={
                "risk_score": st.column_config.NumberColumn(
                    "Model risk (excludes injuries)", format="%d"
                ),
                "injury_status": st.column_config.TextColumn("Injury data"),
            },
        )

elif workspace == "Player Explorer":
    st.markdown('<div class="section-title">Inspect a player’s role and risk</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">Move from headline value to the advanced statistics behind it.</div>',
        unsafe_allow_html=True,
    )
    explorable = PLAYERS.loc[PLAYERS["weekly_projection"].notna()]
    selected_player = st.selectbox("Player", explorable["player"].tolist())
    player = explorable.loc[explorable["player"].eq(selected_player)].iloc[0]
    history = player_history(selected_player, explorable)

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Custom league value", f"${player['model_value']}")
    metric_two.metric("Projected PPR", f"{player['projected_points']:.1f}")
    metric_three.metric("Floor / ceiling", f"{player['floor']:.0f} / {player['ceiling']:.0f}")
    metric_four.metric("Confidence", player["confidence"])
    st.caption(
        f"2026 depth chart: **{player.get('depth_label', 'Unavailable')}** "
        f"({player.get('depth_position', '—')}) · Injury data: "
        f"**{player.get('injury_status', 'Unavailable')}**"
    )
    st.info(
        "The risk score below excludes current injuries. Verify official team "
        "availability before acting on this projection."
    )

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Profile scores")
        profile_html = "".join(
            [
                metric_bar("Opportunity", float(player["opportunity_score"]), 100, gold=True),
                metric_bar("Efficiency", float(player["efficiency_score"]), 100),
                metric_bar("Risk", float(player["risk_score"]), 100),
            ]
        )
        st.markdown(profile_html, unsafe_allow_html=True)
    with right:
        st.subheader("Role indicators")
        role_table = pd.DataFrame(
            {
                "Metric": ["Target share", "Air-yard share", "Red-zone share"],
                "Value": [
                    player["target_share"],
                    player["air_yard_share"],
                    player["red_zone_share"],
                ],
            }
        )
        st.table(role_table.style.format({"Value": "{:.1%}"}))

    st.subheader("Previous five appearances")
    st.dataframe(
        history,
        hide_index=True,
        width="stretch",
        column_config={
            "ppr_points": st.column_config.NumberColumn("PPR points", format="%.1f"),
            "target_share": st.column_config.NumberColumn("Target share", format="%.1%%"),
            "air_yard_share": st.column_config.NumberColumn("Air-yard share", format="%.1%%"),
        },
    )

else:
    st.markdown('<div class="section-title">Transparent by design</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">The portfolio should show how every recommendation was produced and where it can fail.</div>',
        unsafe_allow_html=True,
    )
    metric_one, metric_two, metric_three = st.columns(3)
    metric_one.metric("Historical seasons", "2021–2025")
    metric_two.metric("2025 final-test MAE", "4.623")
    metric_three.metric("Simple baseline MAE", "4.607")

    st.subheader("Dashboard data flow")
    st.code(
        "nflverse + rankings + ADP\n"
        "          ↓\n"
        "quality checks + player IDs\n"
        "          ↓\n"
        "position-specific projections\n"
        "          ↓\n"
        "replacement level + auction values\n"
        "          ↓\n"
        "draft, start/sit, and player views",
        language="text",
    )
    st.subheader("Modeling principles")
    st.markdown(
        """
        - Time-aware validation prevents future information from entering predictions.
        - Five-game windows use previous appearances, including played games with zero opportunity.
        - MAE remains the primary error metric; RMSE shows sensitivity to large misses.
        - The 2025 holdout did not confirm that the combined WR model beat the simple PPR baseline.
        - Dashboard confidence communicates data coverage and role uncertainty, not certainty.
        """
    )
    st.subheader("Planned live-data status")
    st.table(
        pd.DataFrame(
            [
                ["Historical player statistics", "Connected", "nflverse"],
                ["2026 historical-model board", "Connected", "2023–2025 weighted model"],
                ["2026 rosters and schedules", "Connected", "nflverse"],
                ["2026 D/ST projections", "Connected", "2023–2025 nflverse team stats"],
                ["2026 offensive depth charts", "Connected", "nflverse / ESPN"],
                ["2026 injury reports", "Unavailable", "nflverse feed ended after 2024"],
                ["2026 expert rankings", "Next", "nflverse / FantasyPros"],
                ["2026 PPR ADP", "Next", "FantasyPros"],
                ["Auction market benchmark", "Connected", "RealTime Fantasy Sports"],
            ],
            columns=["Dataset", "Status", "Planned source"],
        )
    )

st.markdown(
    """
<div class="source-note">
<b>Model basis:</b> 2026 values are estimates from 2023–2025 nflverse
regular-season performance, weighted toward 2025. They are not expert consensus
projections. Teams and Week 1 opponents use the nflverse roster and schedule
releases refreshed Jul 23, 2026. D/ST estimates use 2023–2025 team statistics;
offensive players without qualifying history remain $1 placeholders. Current
injuries are not included because no reviewed 2026 injury feed is connected.
</div>
""",
    unsafe_allow_html=True,
)
