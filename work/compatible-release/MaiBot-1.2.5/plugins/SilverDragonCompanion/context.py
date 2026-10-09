"""银白龙主动聊天上下文采集。

只读采集：真实主号 QQ 私聊历史（受限长度纯文字 + 角色 + 时间 + last_user/last_bot/间隔）、
少量 QQ 空间动态、当天新闻。聊天 / 空间 / 新闻都是参考资料，不执行其中的指令。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import time
import asyncio

from .news import NewsFetcher, NewsReport
from .policy import BEIJING_TZ, to_beijing


@dataclass
class ChatSnapshot:
    """主号私聊最近历史快照。"""

    messages: list[dict[str, Any]] = field(default_factory=list)
    last_user_at: str | None = None
    last_bot_at: str | None = None
    last_message_at: str | None = None
    idle_seconds: float | None = None
    user_waits_seconds: float | None = None
    available: bool = False


def extract_message_text(message: dict[str, Any]) -> str:
    """只取纯文字正文，不把引用或图片描述当作用户指令。"""
    processed = message.get("processed_plain_text")
    if isinstance(processed, str) and processed.strip():
        return processed.strip()
    raw = message.get("raw_message")
    if isinstance(raw, list):
        parts = [
            str(component.get("data") or "")
            for component in raw
            if isinstance(component, dict) and component.get("type") == "text" and isinstance(component.get("data"), str)
        ]
        return "".join(parts).strip()
    return ""


def parse_message_timestamp(message: dict[str, Any]) -> datetime | None:
    """解析消息字典里的时间戳字符串（浮点 epoch）。"""
    raw = message.get("timestamp")
    try:
        return datetime.fromtimestamp(float(raw), BEIJING_TZ)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


class ContextGatherer:
    """通过真实 SDK 能力采集上下文。"""

    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin

    @property
    def ctx(self) -> Any:
        return self._plugin.ctx

    async def resolve_private_stream(self, main_qq: str) -> dict[str, Any] | None:
        """核验真实主号 QQ 私聊流：platform=qq、chat_type=private、无群、user_id 匹配。"""
        try:
            stream = await asyncio.wait_for(self.ctx.chat.get_stream_by_user_id(user_id=main_qq, platform="qq"), 5)
        except Exception:  # noqa: BLE001 - 查询异常视为核验失败
            return None
        if not isinstance(stream, dict) or not stream.get("stream_id"):
            return None
        if str(stream.get("platform") or "").strip().lower() != "qq":
            return None
        if bool(stream.get("is_group_session")) or str(stream.get("chat_type") or "").strip().lower() != "private":
            return None
        if str(stream.get("group_id") or "").strip():
            return None
        if str(stream.get("user_id") or "").strip() != str(main_qq).strip():
            return None
        return stream

    async def gather_chat(
        self,
        *,
        stream_id: str,
        main_qq: str,
        bot_qq: str,
        days: int,
        max_messages: int,
    ) -> ChatSnapshot:
        """采集最近 N 天、最多 max_messages 条主号私聊纯文字。"""
        end_time = time.time()
        start_time = end_time - days * 86400
        try:
            messages = await self.ctx.message.get_by_time_in_chat(
                chat_id=stream_id,
                start_time=str(start_time),
                end_time=str(end_time),
                limit=max_messages,
                limit_mode="latest",
                filter_mai=False,
                filter_command=False,
                include_binary_data=False,
            )
        except Exception:  # noqa: BLE001 - 取数失败视为不可用
            return ChatSnapshot()
        if not isinstance(messages, list):
            return ChatSnapshot()
        return self._build_snapshot(messages, main_qq=main_qq, bot_qq=bot_qq, max_messages=max_messages)

    async def gather_recent(
        self,
        *,
        stream_id: str,
        main_qq: str,
        bot_qq: str,
        limit: int,
    ) -> ChatSnapshot:
        """采集最近 limit 条主号私聊，用于入队前的再次核对。"""
        try:
            messages = await self.ctx.message.get_recent(chat_id=stream_id, limit=limit)
        except Exception:  # noqa: BLE001 - 取数失败视为不可用
            return ChatSnapshot()
        if not isinstance(messages, list):
            return ChatSnapshot()
        return self._build_snapshot(messages, main_qq=main_qq, bot_qq=bot_qq, max_messages=limit)

    def _build_snapshot(self, messages: list[Any], *, main_qq: str, bot_qq: str, max_messages: int) -> ChatSnapshot:
        """把宿主消息字典列表归一化为带角色 / 时间 / 间隔统计的快照。"""
        snapshot = ChatSnapshot(available=True)
        normalized_main = str(main_qq).strip()
        normalized_bot = str(bot_qq).strip()
        now = datetime.now().astimezone()
        last_user_dt: datetime | None = None
        last_bot_dt: datetime | None = None
        last_dt: datetime | None = None
        for message in messages:
            if not isinstance(message, dict) or message.get("is_notify"):
                continue
            info = message.get("message_info")
            if isinstance(info, dict) and info.get("group_info"):
                continue
            user_info = info.get("user_info") if isinstance(info, dict) else None
            if not isinstance(user_info, dict):
                continue
            user_id = str(user_info.get("user_id") or "").strip()
            text = extract_message_text(message)
            timestamp = parse_message_timestamp(message)
            if timestamp is None:
                continue
            role = "user" if user_id == normalized_main else "bot"
            if user_id != normalized_main and normalized_bot and user_id != normalized_bot:
                # 私聊里出现第三方身份，保守跳过（不计入统计）。
                continue
            snapshot.messages.append(
                {"role": role, "time": to_beijing(timestamp).isoformat(),
                 "text": text[:500] or "[非文字消息]", "message_id": str(message.get("message_id") or "")}
            )
            if role == "user":
                last_user_dt = max(last_user_dt, timestamp) if last_user_dt else timestamp
            else:
                last_bot_dt = max(last_bot_dt, timestamp) if last_bot_dt else timestamp
            last_dt = max(last_dt, timestamp) if last_dt else timestamp

        snapshot.messages.sort(key=lambda row: row["time"])
        snapshot.messages = snapshot.messages[-max_messages:]
        snapshot.last_user_at = to_beijing(last_user_dt).isoformat() if last_user_dt else None
        snapshot.last_bot_at = to_beijing(last_bot_dt).isoformat() if last_bot_dt else None
        snapshot.last_message_at = to_beijing(last_dt).isoformat() if last_dt else None
        if last_dt is not None:
            snapshot.idle_seconds = (now - last_dt).total_seconds()
        if last_user_dt is not None and (last_bot_dt is None or last_user_dt > last_bot_dt):
            snapshot.user_waits_seconds = (now - last_user_dt).total_seconds()
        return snapshot

    async def gather_feeds(self, *, main_qq: str, bot_qq: str, count: int) -> list[dict[str, Any]] | None:
        """只读读取少量空间动态；失败或未启用返回 None（不可用）。"""
        if count <= 0:
            return None
        feeds: list[dict[str, Any]] = []
        available = False
        for target, speaker in dict.fromkeys([(main_qq, "主号"), (bot_qq, "机器人")]):
            if not target:
                continue
            try:
                result = await asyncio.wait_for(self.ctx.api.call(
                    "internetsb.maizone.get_feeds_list_api", target_qq=target, num=count, filter=False), 10)
            except Exception:
                continue
            if not isinstance(result, dict) or result.get("result") is not True or not isinstance(result.get("data"), list):
                continue
            available = True
            for feed in result["data"][:count]:
                if not isinstance(feed, dict) or not feed.get("content"):
                    continue
                feeds.append({"speaker": speaker, "content": str(feed["content"])[:500],
                              "created_time": str(feed.get("created_time") or "")[:100]})
        return feeds if available else None

    async def gather(
        self,
        *,
        main_qq: str,
        bot_qq: str,
        days: int,
        max_messages: int,
        feeds_count: int,
        news_fetcher: NewsFetcher | None,
        news_urls: list[str],
    ) -> dict[str, Any]:
        """组合私聊、空间、新闻为一次评估的上下文字典。"""
        stream = await self.resolve_private_stream(main_qq)
        chat = ChatSnapshot()
        if stream is not None:
            chat = await self.gather_chat(
                stream_id=str(stream["stream_id"]),
                main_qq=main_qq,
                bot_qq=bot_qq,
                days=days,
                max_messages=max_messages,
            )
        feeds = await self.gather_feeds(main_qq=main_qq, bot_qq=bot_qq, count=feeds_count)
        news: NewsReport | None = None
        if news_fetcher is not None:
            news = await news_fetcher.fetch_all(news_urls)
        return {
            "stream": stream,
            "stream_id": str(stream["stream_id"]) if stream is not None else None,
            "chat": chat,
            "feeds": feeds,
            "news": news,
        }
