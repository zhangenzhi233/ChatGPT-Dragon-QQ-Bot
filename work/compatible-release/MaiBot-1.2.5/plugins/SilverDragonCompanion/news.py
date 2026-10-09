"""银白龙主动聊天新闻参考（RSS）。

仅抓取标题 / 来源链接 / 发布时间，按北京时间当天过滤；过期、无日期、抓取或解析失败
都明确标记为不可用，绝不编造当天事件。使用 httpx 与标准库 xml.etree，不新增依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import xml.etree.ElementTree as ET

import httpx

from .policy import BEIJING_TZ, beijing_date, to_beijing


@dataclass
class NewsItem:
    """单条当日新闻（仅标题 / 链接 / 发布时间）。"""

    title: str
    link: str
    pub_date: str
    source: str


@dataclass
class SourceResult:
    """单个 RSS 源的抓取结果。"""

    url: str
    ok: bool
    reason: str = ""
    items: list[NewsItem] = field(default_factory=list)


@dataclass
class NewsReport:
    """一次新闻采集的整体结果。"""

    items: list[NewsItem] = field(default_factory=list)
    sources: list[SourceResult] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool(self.items)


def parse_pubdate(text: str | None) -> datetime | None:
    """解析 RSS pubDate（RFC 822 等）；失败返回 None。"""
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING_TZ)
    return parsed


def parse_rss_bytes(content: bytes, source: str, today: datetime) -> list[NewsItem]:
    """解析 RSS 字节并仅保留北京时间当天的条目。

    解析失败会抛出（由调用方标记该源不可用），无日期条目直接跳过。
    """
    root = ET.fromstring(content)
    channel = root.find("channel")
    items: list[NewsItem] = []
    today_str = beijing_date(today)
    for item in channel.findall("item") if channel is not None else []:
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
        link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
        if not title:
            continue
        published = parse_pubdate(pub_el.text if pub_el is not None else None)
        if published is None:
            continue
        if beijing_date(published) != today_str:
            continue
        items.append(
            NewsItem(
                title=title[:200],
                link=link[:500],
                pub_date=to_beijing(published).isoformat(),
                source=source,
            )
        )
    return items


class NewsFetcher:
    """带大小上限、超时和短缓存的异步 RSS 抓取器。"""

    def __init__(
        self,
        *,
        timeout: int,
        max_bytes: int,
        cache_seconds: int,
        logger: Any,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_bytes = max_bytes
        self._cache_seconds = cache_seconds
        self._logger = logger
        self._transport = transport
        self._cache: dict[tuple[str, ...], tuple[float, NewsReport]] = {}

    async def fetch_all(self, urls: list[str]) -> NewsReport:
        """抓取多个源并合并为当日新闻报告；带短缓存。"""
        key = tuple(str(url or "").strip() for url in urls if str(url or "").strip())
        if not key:
            return NewsReport()
        cached = self._cache.get(key)
        if cached is not None:
            fetched_at, report = cached
            if (datetime.now().timestamp() - fetched_at < self._cache_seconds
                    and beijing_date(datetime.fromtimestamp(fetched_at, BEIJING_TZ)) == beijing_date(datetime.now(BEIJING_TZ))):
                return report

        today = datetime.now(BEIJING_TZ)
        sources: list[SourceResult] = []
        for url in key:
            sources.append(await self._fetch_one(url, today))
        report = NewsReport(
            items=[item for source in sources if source.ok for item in source.items],
            sources=sources,
        )
        self._cache[key] = (datetime.now().timestamp(), report)
        return report

    async def _fetch_one(self, url: str, today: datetime) -> SourceResult:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=self._timeout,
                transport=self._transport,
                headers={"User-Agent": "MaiBot-SilverDragonCompanion/1.0"},
            ) as client:
                content = bytearray()
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        return SourceResult(url=url, ok=False, reason=f"HTTP {response.status_code}")
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > self._max_bytes:
                            return SourceResult(url=url, ok=False, reason=f"响应体超过 {self._max_bytes} 字节")
                        content.extend(chunk)
                items = parse_rss_bytes(content, url, today)
                return SourceResult(url=url, ok=True, items=items)
        except httpx.HTTPError as exc:
            return SourceResult(url=url, ok=False, reason=f"网络错误 {type(exc).__name__}")
        except ET.ParseError:
            return SourceResult(url=url, ok=False, reason="XML 解析失败")
        except Exception as exc:  # noqa: BLE001 - 网络/解析之外的异常也要标记不可用而非崩溃
            self._logger.warning(f"新闻源 {url} 抓取失败：{type(exc).__name__}")
            return SourceResult(url=url, ok=False, reason=type(exc).__name__)
