"""Feed parsing + URL/entry helpers for the firehose (Lane C).

Contract (read-only, owned by Lane B): items keyed by guid_hash
(sha256 of normalized guid||link). This module only *computes* that key.

SWAP POINTS:
- parse_feed stdlib path <-> feedparser-rs (or `feedparser`): set
  USE_FEEDPARSER=1 env or pass kind="feedparser" to try the third-party
  parser first, stdlib as fallback.
- Date parsing below is best-effort; a stricter pipeline would swap in
  `dateutil` / feedparser-rs normalized dates.
"""

from __future__ import annotations

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# SWAP POINT: feedparser / feedparser-rs. Guarded import so stdlib works alone.
try:
    import feedparser  # type: ignore
    _HAS_FEEDPARSER = True
except Exception:  # pragma: no cover
    feedparser = None  # type: ignore
    _HAS_FEEDPARSER = False


def normalize_url(url: str | None) -> str:
    """Normalize a URL for identity (not for fetching)."""
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    scheme = parts.scheme.lower() or "http"
    host = parts.hostname.lower() if parts.hostname else ""
    if not host:
        return url  # opaque / relative: return as-is
    port = parts.port
    # Drop default ports.
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = host if port is None else f"{host}:{port}"
    path = parts.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    # Sort query params for stability; keep blank values.
    query = ""
    if parts.query:
        qsl = parse_qsl(parts.query, keep_blank_values=True)
        qsl.sort()
        query = urlencode(qsl, doseq=True)
    # Drop fragment (identity, not navigation).
    return urlunsplit((scheme, netloc, path, query, ""))


def entry_id(guid: str | None, link: str | None) -> str:
    """Stable PK: sha256(normalized guid + '||' + normalized link).

    Missing guid falls back to link naturally (empty guid side hashes
    as ""). Both empty -> hash of '||' (callers should avoid that).
    """
    g = normalize_url(guid or "")
    l = normalize_url(link or "")
    return hashlib.sha256(f"{g}||{l}".encode("utf-8")).hexdigest()


def _parse_date(raw: str | None) -> str | None:
    """Best-effort date -> ISO 8601 string. Returns original on failure."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    # ISO first (Atom / JSONFeed).
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        pass
    # RFC 2822 (RSS pubDate).
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return raw  # keep raw, never crash the pipeline


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_rss(root: ET.Element) -> list[dict]:
    out: list[dict] = []
    for item in root.iter("item"):
        guid = _text(item.find("guid")) or None
        link = _text(item.find("link")) or None
        title = _text(item.find("title")) or None
        published = _parse_date(_text(item.find("pubDate")) or None)
        # body: description > content:encoded
        body = _text(item.find("description")) or None
        if body is None:
            for child in item:
                if child.tag.endswith("encoded"):
                    body = _text(child) or None
                    break
        out.append({"guid": guid, "link": link, "title": title,
                    "published": published, "body": body})
    return out


def _parse_atom(root: ET.Element) -> list[dict]:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall("a:entry", ns) or root.findall("entry")
    out: list[dict] = []
    for e in entries:
        def find(name: str):
            return e.find(f"a:{name}", ns) if e.find(f"a:{name}", ns) is not None else e.find(name)
        guid = _text(find("id")) or None
        link_el = find("link")
        link = None
        if link_el is not None:
            link = (link_el.get("href") or "").strip() or None
        title = _text(find("title")) or None
        published = _parse_date(_text(find("published")) or _text(find("updated")) or None)
        body = _text(find("content")) or _text(find("summary")) or None
        out.append({"guid": guid, "link": link, "title": title,
                    "published": published, "body": body})
    return out


def _parse_jsonfeed(data: dict) -> list[dict]:
    out: list[dict] = []
    items = data.get("items", []) if isinstance(data, dict) else []
    for it in items:
        if not isinstance(it, dict):
            continue
        guid = it.get("id") or None
        link = it.get("url") or it.get("external_url") or None
        title = it.get("title") or None
        published = _parse_date(it.get("date_published"))
        body = it.get("content_text") or it.get("content_html") or it.get("summary") or None
        out.append({"guid": guid if guid is not None else None,
                    "link": link, "title": title,
                    "published": published, "body": body})
    return out


def _parse_with_feedparser(body: str | bytes) -> list[dict]:
    """SWAP POINT: third-party parse path (feedparser now, feedparser-rs later)."""
    assert _HAS_FEEDPARSER
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    fp = globals().get("feedparser")
    assert fp is not None
    parsed = fp.parse(text)
    out: list[dict] = []
    for e in parsed.entries:
        guid = getattr(e, "id", None) or getattr(e, "guid", None)
        link = getattr(e, "link", None)
        title = getattr(e, "title", None)
        published = _parse_date(getattr(e, "published", None) or getattr(e, "updated", None))
        body_text = getattr(e, "summary", None)
        content = getattr(e, "content", None)
        if content and isinstance(content, list) and content[0].get("value"):
            body_text = content[0]["value"]
        out.append({"guid": guid or None, "link": link or None,
                    "title": title or None, "published": published,
                    "body": body_text or None})
    return out


def parse_feed(body: str | bytes, kind: str = "auto") -> list[dict]:
    """Parse a feed body into [{guid,link,title,published,body}]. No network.

    kind: 'rss' | 'atom' | 'jsonfeed' | 'auto' | 'feedparser'.
    Each dict has keys guid, link, title, published (ISO str|None), body.
    """
    if kind == "feedparser" or (os.getenv("USE_FEEDPARSER") == "1" and kind == "auto"):
        if _HAS_FEEDPARSER:
            try:
                return _parse_with_feedparser(body)
            except Exception:
                pass  # fall through to stdlib
        elif kind == "feedparser":
            raise ImportError("feedparser not installed; stdlib path is the default")

    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    stripped = text.lstrip()

    if kind == "jsonfeed" or (kind == "auto" and stripped.startswith("{")):
        return _parse_jsonfeed(json.loads(text))

    # XML path: RSS vs Atom by root tag.
    root = ET.fromstring(text)
    tag = root.tag.lower()
    if kind == "atom" or "feed" in tag:
        return _parse_atom(root)
    return _parse_rss(root)
