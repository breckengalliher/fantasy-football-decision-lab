"""Narrative-only journalism and reporter context for player outlooks."""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import pandas as pd
import requests


ESPN_NFL_RSS = "https://www.espn.com/espn/rss/nfl/news"
REPORTING_AFFECTS_PROJECTION = False
REPORTER_MARKERS = re.compile(r"\b(reporter|journalist|writer|columnist|editor|covers|beat)\b", re.I)
BLUESKY_REPORTERS = {
    "rapsheet.bsky.social": "Ian Rapoport",
    "tompelissero.bsky.social": "Tom Pelissero",
    "fieldyates.bsky.social": "Field Yates",
    "jjones9.bsky.social": "Jonathan Jones",
    "agetzenberg.bsky.social": "Alaina Getzenberg",
    "bbaby41.bsky.social": "Ben Baby",
    "bepryor.bsky.social": "Brooke Pryor",
    "bynatetaylor.bsky.social": "Nate Taylor",
    "camdasilva.bsky.social": "Cameron DaSilva",
    "coltonpouncy.bsky.social": "Colton Pouncy",
    "jctsports.bsky.social": "Josh Tolentino",
    "jeff-mclane.bsky.social": "Jeff McLane",
    "johnpboyle.bsky.social": "John Boyle",
    "kat-terrell.bsky.social": "Katherine Terrell",
    "kevinseifert.bsky.social": "Kevin Seifert",
    "marcusmosher.bsky.social": "Marcus Mosher",
    "mikereiss.bsky.social": "Mike Reiss",
    "ml-j.bsky.social": "Marcel Louis-Jacques",
    "nickijhabvala.bsky.social": "Nicki Jhabvala",
    "plonnfl.bsky.social": "Pat Leonard",
    "saadyousuf126.bsky.social": "Saad Yousuf",
    "stephenholder-nfl.bsky.social": "Stephen Holder",
    "tampabaytre.bsky.social": "Trevor Sikkema",
    "voiceofthestar.bsky.social": "Patrik Walker",
    "zberm.bsky.social": "Zach Berman",
}


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


def _rss_items(xml_text: str) -> list[dict[str, str]]:
    """Parse provider RSS while tolerating common undeclared HTML entities."""
    cleaned = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)",
        "&amp;",
        xml_text,
    )
    root = ET.fromstring(cleaned)
    return [{
        "title": item.findtext("title") or "",
        "summary": item.findtext("description") or "",
        "link": item.findtext("link") or "",
        "published": item.findtext("pubDate") or "",
    } for item in root.findall(".//item")]


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
    entries = _rss_items(xml_text)
    player_rows = [(_player_key(row.player), str(row.player), str(row.team)) for row in players.itertuples()]
    results = []
    for item in entries:
        title = _clean(item.get("title"))
        description = _clean(item.get("summary") or item.get("description"))
        combined = _player_key(f"{title} {description}")
        for key, player, team in player_rows:
            if key and re.search(rf"(?:^| ){re.escape(key)}(?: |$)", combined):
                results.append({
                    "player": player, "team": team, "source_type": "National journalism",
                    "source_name": "ESPN", "author": "ESPN NFL", "text": f"{title}. {description}",
                    "url": _clean(item.get("link")), "published_at": _clean(item.get("published")),
                })
    return pd.DataFrame(results)


def parse_bluesky_rss(
    xml_text: str,
    players: pd.DataFrame,
    handle: str,
    reporter: str,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Match a curated reporter's public Bluesky RSS feed to roster players."""
    entries = _rss_items(xml_text)
    player_rows = []
    last_name_counts: dict[str, int] = {}
    for row in players.itertuples():
        full = _player_key(row.player)
        last = full.split()[-1] if full else ""
        last_name_counts[last] = last_name_counts.get(last, 0) + 1
        player_rows.append((full, last, str(row.player), str(row.team)))
    results = []
    current = now or datetime.now(timezone.utc)
    for item in entries:
        try:
            published = parsedate_to_datetime(item.get("published", ""))
            published = published if published.tzinfo else published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if published < current - timedelta(days=7):
            continue
        text = _clean(item.get("title") or item.get("summary"))
        searchable = _player_key(text)
        for full, last, player, team in player_rows:
            full_match = full and re.search(rf"(?:^| ){re.escape(full)}(?: |$)", searchable)
            last_match = len(last) >= 4 and last_name_counts.get(last) == 1 and re.search(rf"(?:^| ){re.escape(last)}(?: |$)", searchable)
            if full_match or last_match:
                results.append({
                    "player": player, "team": team, "source_type": "Reporter social",
                    "source_name": reporter, "author": handle, "text": text,
                    "url": _clean(item.get("link")), "published_at": published.isoformat(),
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
    social_players = eligible.head(max_social_players)
    for handle, reporter in BLUESKY_REPORTERS.items():
        try:
            response = get(
                f"https://bsky.app/profile/{handle}/rss",
                timeout=timeout,
                headers={"User-Agent": "FantasyFootballDecisionLab/1.0"},
            )
            response.raise_for_status()
            frame = parse_bluesky_rss(response.text, social_players, handle, reporter, checked)
            records.extend(frame.to_dict("records"))
            social_matches += len(frame)
        except Exception:
            social_errors += 1
    social_status = f"Connected · {social_matches} reporter posts" if social_errors < len(BLUESKY_REPORTERS) else "Unavailable"
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
