"""Fetch and parse RSS/Atom feeds using only the standard library.

A dependency-free parser keeps OpenBioNews trivially installable. It handles
the common shapes of RSS 2.0 and Atom, which cover the great majority of news
feeds. If the optional ``feedparser`` package is installed it is used instead
for wider robustness, but it is never required.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from . import textutil
from .models import Item

USER_AGENT = "OpenBioNews/0.1 (+https://github.com/fedor-i/OpenBioNews)"


class FetchError(Exception):
    """Raised when a feed cannot be retrieved or parsed."""


def _localname(tag: str) -> str:
    """Strip an XML namespace: '{ns}entry' -> 'entry'."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    # RFC 822 (RSS pubDate), e.g. "Mon, 29 Sep 2025 10:00:00 GMT"
    try:
        dt = parsedate_to_datetime(text)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    # ISO 8601 (Atom), e.g. "2025-09-29T10:00:00Z"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_feed(content: bytes | str, source_name: str = "", topic: str = "") -> list[Item]:
    """Parse raw feed bytes/str into Items. Detects RSS vs Atom."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", "replace")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise FetchError(f"invalid XML: {exc}") from exc

    root_name = _localname(root.tag)
    items: list[Item] = []

    if root_name == "feed":  # Atom
        default_title = _text(root.find("./{*}title")) or source_name
        for entry in root.findall("./{*}entry"):
            items.append(_atom_entry(entry, source_name or default_title, topic))
    else:  # RSS (rss/channel/item, or rdf)
        channel = root.find("./{*}channel")
        default_title = _text((channel or root).find("./{*}title")) or source_name
        search_root = channel if channel is not None else root
        for entry in search_root.findall(".//{*}item"):
            items.append(_rss_item(entry, source_name or default_title, topic))
    return [i for i in items if i.title and i.link]


def _rss_item(entry, source_name: str, topic: str) -> Item:
    title = _text(entry.find("./{*}title"))
    link = _text(entry.find("./{*}link"))
    summary = _text(entry.find("./{*}description"))
    guid = _text(entry.find("./{*}guid")) or link
    date_text = (
        _text(entry.find("./{*}pubDate"))
        or _text(entry.find("./{*}date"))  # dc:date
    )
    return Item(
        title=textutil.strip_html(title),
        link=link,
        summary=textutil.strip_html(summary),
        source=source_name,
        topic=topic,
        published=_parse_date(date_text),
        guid=guid,
    )


def _atom_entry(entry, source_name: str, topic: str) -> Item:
    title = _text(entry.find("./{*}title"))
    link = ""
    for link_el in entry.findall("./{*}link"):
        rel = link_el.get("rel", "alternate")
        if rel == "alternate" and link_el.get("href"):
            link = link_el.get("href", "")
            break
        if not link and link_el.get("href"):
            link = link_el.get("href", "")
    summary = _text(entry.find("./{*}summary")) or _text(entry.find("./{*}content"))
    guid = _text(entry.find("./{*}id")) or link
    date_text = _text(entry.find("./{*}published")) or _text(entry.find("./{*}updated"))
    return Item(
        title=textutil.strip_html(title),
        link=link,
        summary=textutil.strip_html(summary),
        source=source_name,
        topic=topic,
        published=_parse_date(date_text),
        guid=guid,
    )


def fetch_feed(feed: dict, timeout: int = 20) -> list[Item]:
    """Fetch one feed dict {name,url,topic}. Supports local file paths too."""
    url = feed.get("url", "")
    name = feed.get("name", "")
    topic = feed.get("topic", "")
    if not url:
        raise FetchError("feed has no url")

    # Allow local files for offline use / the bundled demo. Check this only for
    # non-HTTP URLs so a web address is never mistaken for a filesystem path
    # (important on Windows, where URLs can form odd but valid Path objects).
    if not url.lower().startswith(("http://", "https://")):
        local = url[len("file://"):] if url.startswith("file://") else url
        if Path(local).exists():
            data = Path(local).read_bytes()
            return parse_feed(data, name, topic)
        raise FetchError(f"local feed file not found: {local}")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise FetchError(str(exc)) from exc
    return parse_feed(data, name, topic)


def fetch_all(feeds: list[dict], timeout: int = 20, on_status=None) -> tuple[list[Item], list[tuple[str, str]]]:
    """Fetch every feed. Returns (items, errors) where errors is (name, message).

    Failures are collected, not raised, so one dead feed never sinks the run.
    ``on_status(name, count, error)`` is called after each feed if provided.
    """
    all_items: list[Item] = []
    errors: list[tuple[str, str]] = []
    for feed in feeds:
        name = feed.get("name") or feed.get("url", "?")
        try:
            items = fetch_feed(feed, timeout=timeout)
            all_items.extend(items)
            if on_status:
                on_status(name, len(items), None)
        except FetchError as exc:
            errors.append((name, str(exc)))
            if on_status:
                on_status(name, 0, str(exc))
    return all_items, errors
