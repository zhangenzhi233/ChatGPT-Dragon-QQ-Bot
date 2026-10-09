"""银白龙主动聊天插件入口。

只做生命周期接线：加载 / 卸载 / 配置热更新时启停调度器，不在加载或热重载时伪造启动信号。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import json
import asyncio

from maibot_sdk import MaiBotPlugin

from .config import CompanionConfig
from .scheduler import CompanionScheduler


class SilverDragonCompanionPlugin(MaiBotPlugin):
    """按真实主号私聊、间隔、空间与新闻，由模型自主决定是否主动开口。"""

    config_model = CompanionConfig

    def __init__(self) -> None:
        super().__init__()
        self._scheduler: CompanionScheduler | None = None
        self._readiness_task: asyncio.Task | None = None

    async def on_load(self) -> None:
        """加载时写只读就绪诊断，并仅在启用状态下启动调度器；不生成任何启动信号。"""
        self._scheduler = None
        self._readiness_task = asyncio.create_task(self._delayed_readiness())
        if self.config.plugin.enabled:
            self._scheduler = CompanionScheduler(self, self.ctx.logger)
            await self._scheduler.start()

    async def on_unload(self) -> None:
        """卸载时取消并清理后台任务。"""
        await self._stop_scheduler()
        await self._stop_readiness()

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        """配置热更新：应用本插件配置并重启调度器（取消旧任务）。"""
        del version
        if scope == "self":
            self.set_plugin_config(config_data)
        await self._stop_scheduler()
        await self._stop_readiness()
        self._readiness_task = asyncio.create_task(self._delayed_readiness())
        if self.config.plugin.enabled:
            self._scheduler = CompanionScheduler(self, self.ctx.logger)
            await self._scheduler.start()

    async def _stop_scheduler(self) -> None:
        if self._scheduler is not None:
            await self._scheduler.stop()
            self._scheduler = None

    async def _write_readiness(self) -> None:
        """只读核验真实 SDK 私聊接口，写不含账号的就绪诊断（不调用模型、不发消息）。"""
        main_qq = str(self.config.target.main_qq or "").strip()
        private_stream_verified = False
        history_read_verified = False
        qzone_read_available = False
        if self.config.plugin.enabled and main_qq:
            try:
                from .context import ContextGatherer

                stream = await ContextGatherer(self).resolve_private_stream(main_qq)
                private_stream_verified = stream is not None
                if stream is not None:
                    gatherer = ContextGatherer(self)
                    chat = await gatherer.gather_chat(stream_id=stream["stream_id"], main_qq=main_qq,
                                                     bot_qq=self.config.target.bot_qq, days=7, max_messages=40)
                    history_read_verified = chat.available
                    feeds = await gatherer.gather_feeds(main_qq=main_qq, bot_qq=self.config.target.bot_qq,
                                                       count=self.config.policy.feeds_count)
                    qzone_read_available = feeds is not None
            except Exception:  # noqa: BLE001 - 只读自检失败不计为错误
                private_stream_verified = False
        diagnosis = {
            "checked_at": datetime.now().astimezone().isoformat(),
            "plugin_enabled": bool(self.config.plugin.enabled),
            "main_qq_configured": bool(main_qq),
            "private_stream_verified": private_stream_verified,
            "history_read_verified": history_read_verified,
            "qzone_read_available": qzone_read_available,
            "model_task_name": str(self.config.policy.model_task_name or "utils").strip() or "utils",
            "read_only": True,
            "qq_messages_sent": 0,
            "chat_model_calls": 0,
        }
        output = self.ctx.paths.runtime_dir / "companion-readiness.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    async def _delayed_readiness(self) -> None:
        # 注册结束后再调用 SDK，避免 on_load 期间宿主能力尚未就绪的误报。
        await asyncio.sleep(2)
        await self._write_readiness()

    async def _stop_readiness(self) -> None:
        if self._readiness_task is not None:
            self._readiness_task.cancel()
            try:
                await self._readiness_task
            except asyncio.CancelledError:
                pass
            self._readiness_task = None


def create_plugin() -> SilverDragonCompanionPlugin:
    """创建插件实例。"""
    return SilverDragonCompanionPlugin()
