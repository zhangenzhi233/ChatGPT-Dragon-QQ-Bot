"""离线测试共享工具：用真实 SDK PluginContext + 模拟 transport/LLM。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncio
import time

from maibot_sdk import PluginContext, PluginPaths

from SilverDragonCompanion.plugin import SilverDragonCompanionPlugin

MAIN_QQ = "123456789"
BOT_QQ = "987654321"
STREAM_ID = "sess-main"


def build_stream(*, group: bool = False) -> dict[str, Any]:
    """构造宿主序列化聊天流（与 src/plugin_runtime/capabilities/data.py 对齐）。"""
    if group:
        return {
            "session_id": "sess-group",
            "stream_id": "sess-group",
            "platform": "qq",
            "user_id": "0",
            "user_nickname": "",
            "user_cardname": None,
            "group_id": "111222333",
            "group_name": "测试群",
            "account_id": BOT_QQ,
            "scope": None,
            "is_group_session": True,
            "chat_type": "group",
        }
    return {
        "session_id": STREAM_ID,
        "stream_id": STREAM_ID,
        "platform": "qq",
        "user_id": MAIN_QQ,
        "user_nickname": "主号",
        "user_cardname": None,
        "group_id": None,
        "group_name": None,
        "account_id": BOT_QQ,
        "scope": None,
        "is_group_session": False,
        "chat_type": "private",
    }


def build_message(
    *,
    text: str,
    from_user: bool,
    ts: float,
    message_id: str = "m",
) -> dict[str, Any]:
    """构造宿主序列化消息。"""
    return {
        "message_id": message_id,
        "timestamp": str(ts),
        "platform": "qq",
        "message_info": {
            "user_info": {
                "user_id": MAIN_QQ if from_user else BOT_QQ,
                "user_nickname": "主号" if from_user else "机器人",
                "user_cardname": None,
            },
            "group_info": None,
            "additional_config": {},
        },
        "raw_message": [{"type": "text", "data": text}],
        "processed_plain_text": text,
        "is_notify": False,
        "is_command": False,
        "session_id": STREAM_ID,
    }


class MockTransport:
    """模拟 transport：按真实 SDK 期望返回宿主风格 {success, ...} 包装。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.stream: dict[str, Any] | None = build_stream()
        self.messages: list[dict[str, Any]] = []
        self.recent_messages: list[dict[str, Any]] = []
        self.llm_response: dict[str, Any] = {
            "success": True,
            "response": '{"should_chat": false, "topic": "", "intent": "", "next_check_minutes": 120, "reason": "暂无话题"}',
            "reasoning": "",
            "model_name": "gpt-5.6-sol",
        }
        self.proactive_result: dict[str, Any] = {"success": True, "stream_id": STREAM_ID, "task_id": "t1", "queued": True}
        self.api_result: dict[str, Any] = {"success": True, "result": {"result": True, "message": "ok", "data": []}}
        self.proactive_error: Exception | None = None

    async def rpc_call(self, method: str, plugin_id: str, payload: dict[str, Any], timeout_ms: int | None = None) -> Any:
        del plugin_id, timeout_ms
        capability = payload.get("capability", "")
        args = payload.get("args") or {}
        self.calls.append((capability, dict(args)))
        if capability == "chat.get_stream_by_user_id":
            return {"success": True, "stream": self.stream}
        if capability == "message.get_by_time_in_chat":
            return {"success": True, "messages": list(self.messages)}
        if capability == "message.get_recent":
            return {"success": True, "messages": list(self.recent_messages)}
        if capability == "llm.generate":
            return dict(self.llm_response)
        if capability == "llm.get_available_models":
            return {"success": True, "models": ["utils", "planner", "replyer"]}
        if capability == "maisaka.proactive.trigger":
            if self.proactive_error is not None:
                raise self.proactive_error
            return dict(self.proactive_result)
        if capability == "api.call":
            return dict(self.api_result)
        raise AssertionError(f"unexpected capability: {capability}")

    def proactive_calls(self) -> list[dict[str, Any]]:
        return [args for capability, args in self.calls if capability == "maisaka.proactive.trigger"]


def make_plugin(
    transport: MockTransport,
    tmp_path: Path,
    *,
    enabled: bool = True,
    main_qq: str = MAIN_QQ,
    bot_qq: str = BOT_QQ,
) -> tuple[SilverDragonCompanionPlugin, PluginContext]:
    """构造注入真实 SDK 上下文的插件实例。"""
    ctx = PluginContext(
        plugin_id="local.silver-dragon-companion",
        rpc_call=transport.rpc_call,
        paths=PluginPaths(
            data_dir=tmp_path / "data" / "plugins" / "local.silver-dragon-companion",
            runtime_dir=tmp_path / "temp" / "plugins" / "local.silver-dragon-companion",
        ),
    )
    ctx.paths.data_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    plugin = SilverDragonCompanionPlugin()
    plugin._set_context(ctx)  # noqa: SLF001 - 测试注入
    plugin.set_plugin_config(
        {
            "plugin": {"enabled": enabled, "config_version": "1.0.0"},
            "target": {"main_qq": main_qq, "bot_qq": bot_qq},
            "news": {"enabled": False},
        }
    )
    return plugin, ctx


def run(coro: Any) -> Any:
    """同步执行一个协程。"""
    return asyncio.run(coro)


def epoch_ago(seconds: float) -> float:
    return time.time() - seconds


def silence_response(minutes: int = 120) -> dict[str, Any]:
    return {
        "success": True,
        "response": (
            '{"should_chat": false, "topic": "", "intent": "", "next_check_minutes": %d, "reason": "暂无话题"}'
            % minutes
        ),
        "reasoning": "",
        "model_name": "gpt-5.6-sol",
    }


def chat_response(topic: str, minutes: int = 90) -> dict[str, Any]:
    return {
        "success": True,
        "response": (
            '{"should_chat": true, "topic": "%s", "intent": "聊%s", "next_check_minutes": %d, "reason": "合适"}' % (topic, topic, minutes)
        ),
        "reasoning": "",
        "model_name": "gpt-5.6-sol",
    }
