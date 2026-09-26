"""Tests for parse.py (Lane C). Inline fixtures, no network."""

from parse import entry_id, normalize_url, parse_feed

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
<item><guid>abc-123</guid><link>https://ex.com/a</link>
<title>Hello</title><pubDate>Tue, 09 Sep 2026 10:00:00 GMT</pubDate>
<description>Body one</description></item>
<item><link>https://ex.com/b</link><title>No guid</title>
<description>Body two</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><id>tag:ex.com,2026:1</id><link href="https://ex.com/c"/>
<title>Atom one</title><published>2026-09-09T10:00:00Z</published>
<summary>Summary C</summary></entry>
</feed>"""

JSONFEED = """{"version": "https://jsonfeed.org/version/1.1",
"items": [{"id": "j-1", "url": "https://ex.com/d", "title": "JSON one",
"date_published": "2026-09-09T10:00:00Z", "content_text": "Body D"}]}"""


def test_rss_shape():
    items = parse_feed(RSS, "rss")
    assert len(items) == 2
    assert items[0]["guid"] == "abc-123"
    assert items[0]["link"] == "https://ex.com/a"
    assert items[0]["title"] == "Hello"
    assert items[0]["published"] and "2026-09-09" in items[0]["published"]
    assert items[0]["body"] == "Body one"
    assert items[1]["guid"] is None  # missing guid -> None, link fallback


def test_atom_shape():
    items = parse_feed(ATOM, "atom")
    assert len(items) == 1
    assert items[0]["guid"] == "tag:ex.com,2026:1"
    assert items[0]["link"] == "https://ex.com/c"
    assert items[0]["body"] == "Summary C"


def test_jsonfeed_shape():
    items = parse_feed(JSONFEED, "jsonfeed")
    assert len(items) == 1
    assert items[0]["guid"] == "j-1"
    assert items[0]["body"] == "Body D"


def test_auto_detect():
    assert len(parse_feed(RSS)) == 2
    assert len(parse_feed(ATOM)) == 1
    assert len(parse_feed(JSONFEED)) == 1


def test_entry_id_stable():
    a = entry_id("abc-123", "https://ex.com/a")
    assert a == entry_id("abc-123", "https://ex.com/a")
    assert len(a) == 64
    # URL normalization: fragment + trailing slash don't change identity
    assert entry_id("abc-123", "https://ex.com/a") == entry_id("abc-123", "https://ex.com/a/#frag")


def test_missing_guid_falls_back_to_link():
    with_guid = entry_id("abc-123", "https://ex.com/a")
    no_guid = entry_id(None, "https://ex.com/a")
    assert no_guid == entry_id("", "https://ex.com/a")  # stable fallback
    assert no_guid != with_guid  # guid still distinguishes when present


def test_normalize_url_host_case_and_default_port():
    assert normalize_url("HTTPS://EX.com:443/a/") == normalize_url("https://ex.com/a")
