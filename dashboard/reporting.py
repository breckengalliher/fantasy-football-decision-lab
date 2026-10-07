"""Narrative-only journalism and reporter context for player outlooks."""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pandas as pd
import requests


ESPN_NFL_RSS = "https://www.espn.com/espn/rss/nfl/news"
BLUESKY_SEARCH = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
REPORTING_AFFECTS_PROJECTION = False
REPORTER_MARKERS = re.compile(r"\b(reporter|journalist|writer|columnist|editor|covers|beat)\b", re.I)


@dataclass(frozen=True)
class ReportingContext:
    records: pd.DataFrame
    checked_at: str
    journalism_status: str
    social_status: str


def _clean(value: Any) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _player_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def _themes(text: str) -> list[str]:
    lowered = text.casefold()
    themes = []
    checks = [
        ("availability", ("injur", "questionable", "doubtful", "practice", "inactive", "return")),
        ("workload", ("target", "touch", "snap", "workload", "committee", "role")),
        ("quarterback situation", ("quarterback", " qb ", "starter", "backup")),
        ("recent performance", ("breakout", "struggl", "production", "yards", "touchdown")),
    ]
    padded = f" {lowered} "
    for label, words in checks:
        if any(word in padded for word in words):
            themes.append(label)
    return themes


def summarize_reporting(player: str, records: pd.DataFrame) -> str:
    """Create a concise paraphrase from reporting themes, never a model input."""
    if records.empty:
        return ""
    all_themes: list[str] = []
    for text in records.get("text", pd.Series(dtype=str)).fillna(""):
        all_themes.extend(_themes(str(text)))
    ordered = list(dict.fromkeys(all_themes))
    source_names = list(dict.fromkeys(records.get("source_name", pd.Series(dtype=str)).dropna().astype(str)))
    source_phrase = " and ".join(source_names[:2]) if source_names else "recent coverage"
    first = str(player).split()[0]
    if ordered:
        focus = " and ".join(ordered[:2])
        return f"The latest coverage from {source_phrase} is focused on {first}'s {focus}. It adds useful context, but it does not change the projection or Start/Sit label."
    return f"Recent coverage from {source_phrase} does not identify a clear role or availability change for {first}. It is included for context only."


def parse_espn_rss(xml_text: str, players: pd.DataFrame) -> pd.DataFrame:
    """Match official ESPN NFL feed items to exact player names."""
    root = ET.fromstring(xml_text)
    player_rows = [(_player_key(row.player), str(row.player), str(row.team)) for row in players.itertuples()]
    results = []
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title"))
        description = _clean(item.findtext("description"))
        combined = _player_key(f"{title} {description}")
        for key, player, team in player_rows:
            if key and re.search(rf"(?:^| ){re.escape(key)}(?: |$)", combined):
                results.append({
                    "player": player, "team": team, "source_type": "National journalism",
                    "source_name": "ESPN", "author": "ESPN NFL", "text": f"{title}. {description}",
                    "url": _clean(item.findtext("link")), "published_at": _clean(item.findtext("pubDate")),
                })
    return pd.DataFrame(results)


def _parse_bsky_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_bluesky_posts(payload: dict[str, Any], player: str, team: str, now: datetime | None = None) -> pd.DataFrame:
    """Keep recent public posts from accounts whose profiles identify reporting work."""
    current = now or datetime.now(timezone.utc)
    rows = []
    for post in payload.get("posts", []):
        author = post.get("author", {}) or {}
        description = _clean(author.get("description"))
        if not REPORTER_MARKERS.search(description):
            continue
        record = post.get("record", {}) or {}
        created = _parse_bsky_time(record.get("createdAt"))
        if created is None or created < current - timedelta(days=7):
            continue
        uri = str(post.get("uri", ""))
        rkey = uri.rsplit("/", 1)[-1]
        handle = str(author.get("handle", ""))
        if not handle or not rkey:
            continue
        rows.append({
            "player": player, "team": team, "source_type": "Reporter social",
            "source_name": _clean(author.get("displayName")) or handle,
            "author": handle, "text": _clean(record.get("text")),
            "url": f"https://bsky.app/profile/{handle}/post/{rkey}",
            "published_at": created.isoformat(),
        })
    return pd.DataFrame(rows)


def load_reporting_context(
    players: pd.DataFrame,
    timeout: int = 15,
    max_social_players: int = 48,
    get: Callable[..., Any] = requests.get,
) -> ReportingContext:
    """Fetch reporting once in the cloud refresh; failures remain non-fatal."""
    checked = datetime.now(timezone.utc)
    eligible = players[["player", "team", "position", "projected_ppr"]].drop_duplicates("player")
    eligible = eligible.sort_values(["position", "projected_ppr"], ascending=[True, False]).groupby("position", group_keys=False).head(12)
    records = []
    try:
        response = get(ESPN_NFL_RSS, timeout=timeout, headers={"User-Agent": "FantasyFootballDecisionLab/1.0"})
        response.raise_for_status()
        frame = parse_espn_rss(response.text, eligible)
        records.extend(frame.to_dict("records"))
        journalism_status = f"Connected · {len(frame)} matched items"
    except Exception as error:
        journalism_status = f"Unavailable · {type(error).__name__}"

    social_matches = 0
    social_errors = 0
    for row in eligible.head(max_social_players).itertuples():
        try:
            response = get(
                BLUESKY_SEARCH,
                params={"q": f'"{row.player}" NFL', "limit": 8, "sort": "latest"},
                timeout=timeout,
                headers={"User-Agent": "FantasyFootballDecisionLab/1.0"},
            )
            response.raise_for_status()
            frame = parse_bluesky_posts(response.json(), str(row.player), str(row.team), checked)
            records.extend(frame.to_dict("records"))
            social_matches += len(frame)
        except Exception:
            social_errors += 1
    social_status = f"Connected · {social_matches} reporter posts" if social_errors < len(eligible.head(max_social_players)) else "Unavailable"
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame = frame.drop_duplicates(["player", "url"]).sort_values("published_at", ascending=False)
    return ReportingContext(frame, checked.isoformat(), journalism_status, social_status)


def enrich_with_reporting(board: pd.DataFrame, context: ReportingContext) -> pd.DataFrame:
    """Attach summaries and links without modifying any projection columns."""
    result = board.copy()
    result["reporting_summary"] = ""
    result["reporting_sources_json"] = "[]"
    result["reporting_checked_at"] = context.checked_at
    if context.records.empty:
        return result
    for player, group in context.records.groupby("player"):
        mask = result["player"].eq(player)
        if not mask.any():
            continue
        selected = group.head(3)
        result.loc[mask, "reporting_summary"] = summarize_reporting(player, selected)
        sources = selected[["source_name", "source_type", "url", "published_at"]].to_dict("records")
        result.loc[mask, "reporting_sources_json"] = json.dumps(sources)
    return result
