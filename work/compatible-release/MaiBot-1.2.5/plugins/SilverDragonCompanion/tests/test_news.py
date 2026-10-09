"""新闻 RSS 解析与异常处理测试。"""

from __future__ import annotations

from datetime import datetime, timedelta

import asyncio
import logging

import httpx

from SilverDragonCompanion.news import NewsFetcher, parse_pubdate, parse_rss_bytes
from SilverDragonCompanion.policy import BEIJING_TZ, beijing_date


def _today_bj() -> datetime:
    return datetime.now(BEIJING_TZ)


def _rss(items: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<rss version=\"2.0\"><channel><title>t</title>"
        f"{items}</channel></rss>"
    ).encode("utf-8")


def _item(title: str, pub: str, link: str = "https://example.com/a") -> str:
    return f"<item><title>{title}</title><link>{link}</link><pubDate>{pub}</pubDate></item>"


def test_parse_pubdate_rfc822():
    parsed = parse_pubdate("Wed, 08 Oct 2026 10:00:00 +0800")
    assert parsed is not None
    assert parsed.hour == 10
    assert parse_pubdate("") is None
    assert parse_pubdate("garbage") is None
    assert parse_pubdate(None) is None


def test_parse_rss_keeps_only_today():
    today = _today_bj()
    today_rfc = today.strftime("%a, %d %b %Y %H:%M:%S +0800")
    yesterday = (today - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S +0800")
    content = _rss(_item("今日新闻", today_rfc) + _item("昨日新闻", yesterday) + _item("无日期", ""))
    items = parse_rss_bytes(content, "src", today)
    assert [item.title for item in items] == ["今日新闻"]
    assert items[0].link == "https://example.com/a"
    assert beijing_date(today) in items[0].pub_date


def test_parse_rss_invalid_xml_raises():
    try:
        parse_rss_bytes(b"<not-xml", "src", _today_bj())
        raise AssertionError("应抛出解析异常")
    except Exception as exc:  # noqa: BLE001
        assert type(exc).__name__ == "ParseError"


def _mock_transport(body: bytes, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handler)


def test_fetch_all_marks_ok_and_merges():
    today = _today_bj()
    today_rfc = today.strftime("%a, %d %b %Y %H:%M:%S +0800")
    body = _rss(_item("A", today_rfc))
    fetcher = NewsFetcher(
        timeout=5, max_bytes=100000, cache_seconds=300, logger=logging.getLogger("t"), transport=_mock_transport(body)
    )

    async def go():
        return await fetcher.fetch_all(["https://x/rss"])

    report = asyncio.run(go())
    assert report.available is True
    assert [item.title for item in report.items] == ["A"]


def test_fetch_all_marks_http_error_unavailable():
    fetcher = NewsFetcher(
        timeout=5, max_bytes=100000, cache_seconds=300, logger=logging.getLogger("t"), transport=_mock_transport(b"", status=500)
    )

    async def go():
        return await fetcher.fetch_all(["https://x/rss"])

    report = asyncio.run(go())
    assert report.available is False
    assert report.sources[0].ok is False
    assert "500" in report.sources[0].reason


def test_fetch_all_oversize_unavailable():
    fetcher = NewsFetcher(
        timeout=5, max_bytes=10, cache_seconds=300, logger=logging.getLogger("t"), transport=_mock_transport(b"x" * 100)
    )

    async def go():
        return await fetcher.fetch_all(["https://x/rss"])

    report = asyncio.run(go())
    assert report.available is False
    assert report.sources[0].reason
