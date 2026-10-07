from datetime import datetime, timezone

import pandas as pd

from dashboard.reporting import (
    REPORTING_AFFECTS_PROJECTION,
    ReportingContext,
    enrich_with_reporting,
    parse_bluesky_posts,
    parse_espn_rss,
    summarize_reporting,
)


def test_espn_feed_matches_exact_player_name():
    xml = """<rss><channel><item><title>CeeDee Lamb returns to full practice</title>
    <description>Dallas expects its receiver to handle his normal role.</description>
    <link>https://example.com/lamb</link><pubDate>Wed, 07 Oct 2026 12:00:00 GMT</pubDate>
    </item></channel></rss>"""
    players = pd.DataFrame([{"player": "CeeDee Lamb", "team": "DAL"}, {"player": "Nico Collins", "team": "HOU"}])
    result = parse_espn_rss(xml, players)
    assert result["player"].tolist() == ["CeeDee Lamb"]
    assert result.loc[0, "source_type"] == "National journalism"


def test_bluesky_keeps_recent_reporter_posts_only():
    payload = {"posts": [
        {"author": {"handle": "beat.example", "displayName": "Local Beat", "description": "Reporter covering the Dallas Cowboys"},
         "record": {"text": "CeeDee Lamb practiced in full today", "createdAt": "2026-10-07T12:00:00Z"},
         "uri": "at://did:plc:test/app.bsky.feed.post/abc"},
        {"author": {"handle": "fan.example", "displayName": "A Fan", "description": "football fan"},
         "record": {"text": "Start Lamb", "createdAt": "2026-10-07T12:00:00Z"},
         "uri": "at://did:plc:fan/app.bsky.feed.post/def"},
    ]}
    result = parse_bluesky_posts(payload, "CeeDee Lamb", "DAL", datetime(2026, 10, 7, 13, tzinfo=timezone.utc))
    assert result["author"].tolist() == ["beat.example"]
    assert result.loc[0, "url"].endswith("/post/abc")


def test_reporting_summary_is_natural_and_explicitly_non_model():
    records = pd.DataFrame([{"source_name": "ESPN", "text": "Player returned to full practice and expects normal workload."}])
    text = summarize_reporting("CeeDee Lamb", records)
    assert "availability" in text
    assert "workload" in text
    assert "does not change the projection" in text


def test_reporting_enrichment_never_changes_projection_columns():
    assert REPORTING_AFFECTS_PROJECTION is False
    board = pd.DataFrame([{"player": "CeeDee Lamb", "team": "DAL", "projected_ppr": 18.5, "median_ppr": 18.5, "floor_ppr": 10.0, "ceiling_ppr": 27.0}])
    records = pd.DataFrame([{"player": "CeeDee Lamb", "team": "DAL", "source_name": "ESPN", "source_type": "National journalism", "url": "https://example.com", "published_at": "2026-10-07", "text": "Full practice and normal workload"}])
    context = ReportingContext(records, "2026-10-07T13:00:00Z", "Connected", "Connected")
    result = enrich_with_reporting(board, context)
    for column in ["projected_ppr", "median_ppr", "floor_ppr", "ceiling_ppr"]:
        assert result.loc[0, column] == board.loc[0, column]
    assert result.loc[0, "reporting_summary"]
