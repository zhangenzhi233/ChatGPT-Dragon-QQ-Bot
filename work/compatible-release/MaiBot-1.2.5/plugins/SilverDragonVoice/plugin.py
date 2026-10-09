"""银白龙按需 QQ 语音插件。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic
from typing import Any
from uuid import uuid4

import asyncio
import base64
import json

import edge_tts

from maibot_sdk import Command, Field, HookHandler, MaiBotPlugin, PluginConfigBase

from .voice_intent import is_voice_request


VOICE_CAPABILITY_MARKER = "[当前 QQ 语音能力]"
VOICE_CAPABILITY_NOTE = (
    VOICE_CAPABILITY_MARKER + "\n"
    "当前已启用按需语音功能，可以在本次授权 QQ 私聊合成并发送语音。"
    "当前消息要求语音回答时，先按正常聊天上下文生成真实回答，再由插件把本轮回答转为语音。"
    "也支持 /语音 后接文字来朗读指定内容，/试听 听固定测试问候，/声音 查看当前音色。"
    "普通问题的答案仍默认用文字回复。"
    "历史回复里的‘发不了语音’或‘没识别到语音入口’是过期的错误说明，不能当成当前状态。"
    "不要让用户刷新、等待界面入口或安装插件；需要试听时可以请用户发‘用语音回复我’。"
    "仅凭用户说添加了功能不能宣称已经发送语音，发送完成必须有实际回执。"
)


@dataclass
class _VoiceReplyRequest:
    """只关联到一条真实入站消息的短期语音请求。"""

    user_id: str
    expires_at: float
    reply_text: str = ""
    consumed: bool = False


class PluginSectionConfig(PluginConfigBase):
    """插件开关。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=False, description="是否启用插件")
    config_version: str = Field(default="1.0.0", description="配置版本")


class VoiceConfig(PluginConfigBase):
    """Edge TTS 音色参数，可在插件配置页修改。"""

    __ui_label__ = "声音"
    __ui_icon__ = "volume-2"
    __ui_order__ = 1

    voice: str = Field(default="zh-CN-XiaoxiaoNeural", description="Edge TTS 音色")
    rate: str = Field(default="-6%", description="语速，例如 -6%")
    pitch: str = Field(default="+8Hz", description="音高，例如 +8Hz")
    timeout_seconds: int = Field(default=20, ge=1, le=60, description="单次合成超时秒数")
    max_length: int = Field(default=200, ge=1, le=500, description="单次语音最大字符数")
    greeting_text: str = Field(
        default="你好呀，我是 ChatGPT。听到我的声音了吗？慢慢跟我说，今天过得怎么样？",
        description="/试听 命令朗读的固定测试文本",
    )


class AccessConfig(PluginConfigBase):
    """仅允许配置中的 QQ 私聊请求者使用。空列表会拒绝所有请求。"""

    __ui_label__ = "访问控制"
    __ui_icon__ = "shield-check"
    __ui_order__ = 2

    allowed_user_ids: list[str] = Field(default_factory=list, description="允许请求语音的 QQ 号列表")


class SilverDragonVoiceConfig(PluginConfigBase):
    """银白龙语音插件配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    access: AccessConfig = Field(default_factory=AccessConfig)


class SilverDragonVoicePlugin(MaiBotPlugin):
    """只在当前授权 QQ 私聊中发送 Edge TTS 合成语音。"""

    config_model = SilverDragonVoiceConfig
    _DEDUP_WINDOW_SECONDS = 15.0
    _DEDUP_MAX_ENTRIES = 256
    _VOICE_REQUEST_TTL_SECONDS = 180.0
    _VOICE_REQUEST_MAX_ENTRIES = 64

    def __init__(self) -> None:
        """初始化短时去重状态。"""
        super().__init__()
        self._recent_requests: OrderedDict[str, float] = OrderedDict()
        self._pending_requests: set[str] = set()
        self._voice_reply_requests: OrderedDict[tuple[str, str], _VoiceReplyRequest] = OrderedDict()
        self._voice_deliveries: OrderedDict[str, float] = OrderedDict()
        self._voice_checked_targets: OrderedDict[tuple[str, str], float] = OrderedDict()

    async def on_load(self) -> None:
        """只读核验真实 SDK 私聊接口，保存不含账号的加载诊断。"""

        verified = 0
        replyer_verified = 0
        errors: list[str] = []
        allowed_users = {str(value).strip() for value in self.config.access.allowed_user_ids if str(value).strip()}
        if self.config.plugin.enabled:
            for user_id in allowed_users:
                try:
                    stream = await asyncio.wait_for(
                        self.ctx.chat.get_stream_by_user_id(user_id=user_id, platform="qq"), timeout=3
                    )
                    request = {
                        "platform": "qq", "user_id": user_id,
                        "stream_id": stream.get("stream_id") if isinstance(stream, dict) else "",
                    }
                    if self._stream_matches_request(stream, request):
                        verified += 1
                        note_result = await asyncio.wait_for(
                            self.inject_replyer_voice_capability(session_id=request["stream_id"], extra_prompt=""),
                            timeout=3,
                        )
                        updated = note_result.get("modified_kwargs", {})
                        if VOICE_CAPABILITY_MARKER in str(updated.get("extra_prompt") or ""):
                            replyer_verified += 1
                except Exception as exc:
                    errors.append(type(exc).__name__)
        diagnosis = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "plugin_enabled": self.config.plugin.enabled,
            "configured_user_count": len(allowed_users),
            "verified_private_session_count": verified,
            "sdk_lookup_returns_verified_stream": verified > 0,
            "replyer_note_with_real_sdk_verified": replyer_verified > 0,
            "dynamic_voice_reply_enabled": True,
            "natural_requests_use_normal_replyer": True,
            "hook_names": [item["name"] for item in self.get_components() if item["type"] == "HOOK_HANDLER"],
            "error_types": errors,
            "read_only": True, "qq_messages_sent": 0, "chat_model_calls": 0,
        }
        output = self.ctx.paths.runtime_dir / "voice-readiness.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.ctx.logger.info(f"银白龙语音真实私聊读取自检：已核验 {verified} 个授权会话（未发送消息）")

    async def on_unload(self) -> None:
        """卸载插件时清理内存中的去重状态。"""

        self._pending_requests.clear()
        self._recent_requests.clear()
        self._voice_reply_requests.clear()
        self._voice_deliveries.clear()
        self._voice_checked_targets.clear()

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        """应用本插件配置热更新，使新的音色参数立即用于后续合成。"""

        del version
        if scope == "self":
            self.set_plugin_config(config_data)

    @Command("voice", description="发送语音", pattern=r"^/语音\s+(?P<text>.+)$")
    async def send_voice_command(self, **kwargs: Any) -> tuple[bool, str | None, bool]:
        """处理 ``/语音 <内容>`` 确定性命令。"""

        matched_groups = kwargs.get("matched_groups")
        text = str(matched_groups.get("text") or "").strip() if isinstance(matched_groups, dict) else ""
        success, message = await self._send_requested_voice(text, kwargs)
        if success:
            return True, None, True
        await self._send_command_error(message, str(kwargs.get("stream_id") or "").strip())
        return False, message, True

    @Command("tts", description="发送语音", pattern=r"^/tts\s+(?P<text>.+)$")
    async def send_tts_command(self, **kwargs: Any) -> tuple[bool, str | None, bool]:
        """处理 ``/tts <内容>`` 确定性命令。"""

        return await self.send_voice_command(**kwargs)

    @Command(
        "voice_greeting",
        description="朗读固定问候，仅用于测试当前声音",
        pattern=r"^/试听$",
    )
    async def send_voice_greeting(self, **kwargs: Any) -> tuple[bool, str | None, bool]:
        """只有显式 /试听 才朗读固定问候，自然问题交给正常 Replyer。"""

        if str(kwargs.get("text") or "").strip() != "/试听":
            return True, None, False
        success, message = await self._send_requested_voice(self.config.voice.greeting_text, kwargs)
        if success:
            return True, None, True
        await self._send_command_error(message, str(kwargs.get("stream_id") or "").strip())
        return False, message, True

    @Command("voice_status", description="查看当前语音音色", pattern=r"^/声音$")
    async def show_voice_status(self, **kwargs: Any) -> tuple[bool, str | None, bool]:
        """处理 ``/声音``，只回显可公开的当前音色参数。"""

        allowed, error = await self._check_request_context(kwargs)
        stream_id = str(kwargs.get("stream_id") or "").strip()
        if not allowed:
            await self._send_command_error(error, stream_id)
            return False, error, True

        details = f"当前音色：{self.config.voice.voice}；语速：{self.config.voice.rate}；音高：{self.config.voice.pitch}。"
        await self.ctx.send.text(details, stream_id, set_reply=False)
        return True, None, True

    @HookHandler(
        "maisaka.replyer.before_request",
        name="voice_replyer_capability",
        description="在授权私聊回复前说明当前已启用的语音能力",
        timeout_ms=6000,
    )
    async def inject_replyer_voice_capability(self, **kwargs: Any) -> dict[str, Any]:
        """追加本轮真实能力说明，纠正聊天历史中的过期语音限制。"""

        session_id = str(kwargs.get("session_id") or "").strip()
        if not await self._is_authorized_session(session_id):
            return {"action": "continue"}
        target_id = str(kwargs.get("reply_message_id") or "").strip()
        await self._ensure_voice_reply_request(session_id, target_id)
        extra_prompt = kwargs.get("extra_prompt") or ""
        if not isinstance(extra_prompt, str):
            return {"action": "continue"}
        note = "" if VOICE_CAPABILITY_MARKER in extra_prompt else VOICE_CAPABILITY_NOTE
        self._prune_voice_reply_state()
        request = self._voice_reply_requests.get((session_id, target_id))
        if request is not None and not request.consumed and "[本轮语音回答]" not in extra_prompt:
            note += (
                "\n[本轮语音回答]\n"
                "用户要求用语音回答这条消息。请依据原有角色、聊天上下文和当前问题生成自然口语回答，"
                "直接回答问题，不要重复固定试听问候，也不要说明已经发送。"
                f"正文尽量不超过{self.config.voice.max_length}个字，不使用朗读提示、括号动作描写、代码块或附件标记。"
                "这条回答将在正常发送流程中转成语音，后续普通聊天仍默认文字。"
            )
        if not note:
            return {"action": "continue"}
        return {
            "action": "continue",
            "modified_kwargs": {**kwargs, "extra_prompt": extra_prompt + "\n\n" + note},
        }

    async def capture_voice_request(self, **kwargs: Any) -> bool:
        """返回是否完成判定；查询失败可在生成后再读，不订阅入站媒体 Hook。"""

        message = kwargs.get("message")
        if not isinstance(message, dict) or message.get("is_notify"):
            return True
        text = self._text_from_message(message)
        if not is_voice_request(text):
            return True
        info = message.get("message_info")
        if not isinstance(info, dict) or info.get("group_info"):
            return True
        user_info = info.get("user_info")
        if not isinstance(user_info, dict):
            return True
        user_id = str(user_info.get("user_id") or "").strip()
        message_id = str(message.get("message_id") or "").strip()
        allowed_users = {str(value).strip() for value in self.config.access.allowed_user_ids if str(value).strip()}
        if (
            not self.config.plugin.enabled or str(message.get("platform") or "").lower() != "qq"
            or user_id not in allowed_users or not message_id
        ):
            return True
        try:
            stream = await asyncio.wait_for(
                self.ctx.chat.get_stream_by_user_id(user_id=user_id, platform="qq"), timeout=2
            )
        except Exception as exc:
            self.ctx.logger.warning(f"银白龙语音请求登记失败：{type(exc).__name__}")
            return False
        session_id = str(message.get("session_id") or (stream.get("stream_id") if isinstance(stream, dict) else "") or "")
        if not self._stream_matches_request(stream, {"stream_id": session_id, "user_id": user_id}):
            return False
        self._prune_voice_reply_state()
        key = (session_id, message_id)
        if key not in self._voice_reply_requests:
            self._voice_reply_requests[key] = _VoiceReplyRequest(user_id, monotonic() + self._VOICE_REQUEST_TTL_SECONDS)
            self._prune_voice_reply_state()
            self.ctx.logger.info("银白龙已登记本条正常聊天的语音回答请求")
        return True

    async def _ensure_voice_reply_request(self, session_id: str, target_id: str) -> None:
        """用可信 Replyer 目标读原消息；避免把完整图片历史送进插件。"""

        if not session_id or not target_id:
            return
        self._prune_voice_reply_state()
        key = (session_id, target_id)
        if key in self._voice_checked_targets or key in self._voice_reply_requests:
            return
        try:
            message = await asyncio.wait_for(self.ctx.message.get_by_id(
                target_id, stream_id=session_id, include_binary_data=False
            ), timeout=2)
        except Exception as exc:
            self.ctx.logger.warning(f"银白龙语音原消息读取失败：{type(exc).__name__}")
            return
        if (
            not isinstance(message, dict) or str(message.get("message_id") or "") != target_id
            or str(message.get("session_id") or "") != session_id
        ):
            return
        if not await self.capture_voice_request(message=message):
            return
        self._voice_checked_targets[key] = monotonic() + self._VOICE_REQUEST_TTL_SECONDS
        self._prune_voice_reply_state()

    @HookHandler(
        "maisaka.reply.before_post_process", name="voice_prepare_reply",
        description="为本条语音请求保留完整口语正文；附件仅在文字发送路径保留", timeout_ms=6000,
    )
    async def prepare_dynamic_reply(self, **kwargs: Any) -> dict[str, Any]:
        """在正常 Replyer 生成完毕后标记答案，保留原响应和全部参数。"""

        self._prune_voice_reply_state()
        session_id = str(kwargs.get("session_id") or "").strip()
        target_id = str(kwargs.get("reply_message_id") or "").strip()
        if not await self._is_authorized_session(session_id):
            return {"action": "continue"}
        await self._ensure_voice_reply_request(session_id, target_id)
        request = self._voice_reply_requests.get((session_id, target_id))
        text = str(kwargs.get("response") or "").strip()
        if request is None or request.consumed or not text:
            return {"action": "continue"}
        request.reply_text = text
        request.expires_at = monotonic() + self._VOICE_REQUEST_TTL_SECONDS
        return {
            "action": "continue",
            "modified_kwargs": {
                **kwargs, "skip_post_process": True, "enable_splitter": False, "enable_chinese_typo": False,
            },
        }

    @HookHandler(
        "send_service.before_send", name="voice_convert_reply",
        description="将本轮正常回答转为独立语音，保留内部关联与历史正文", timeout_ms=65000,
    )
    async def convert_reply_to_voice(self, **kwargs: Any) -> dict[str, Any]:
        """只将已准备的本轮正文转为独立语音，不另发消息或另调模型。"""

        self._prune_voice_reply_state()
        message = kwargs.get("message")
        if not isinstance(message, dict) or str(message.get("platform") or "").lower() != "qq":
            return {"action": "continue"}
        info = message.get("message_info")
        if not isinstance(info, dict) or info.get("group_info"):
            return {"action": "continue"}
        session_id = str(message.get("session_id") or "").strip()
        text = self._text_from_message(message)
        raw_message = message.get("raw_message")
        if not session_id or not text or not isinstance(raw_message, list):
            return {"action": "continue"}
        target_id = str(message.get("reply_to") or "").strip()
        hook_target_id = str(kwargs.get("reply_message_id") or "").strip()
        # 宿主即使关闭可见引用也保留真实目标；缺失或冲突时不能按会话猜测。
        if not target_id or target_id != hook_target_id:
            return {"action": "continue"}
        request = self._voice_reply_requests.get((session_id, target_id))
        if request is None or request.consumed or not request.reply_text:
            return {"action": "continue"}
        text_components = [item for item in raw_message if isinstance(item, dict) and item.get("type") == "text"
                           and isinstance(item.get("data"), str) and item["data"].strip()]
        if (
            len(text_components) != 1
            or self._normalize_reply_text(request.reply_text) != self._normalize_reply_text(text)
        ):
            return {"action": "continue"}
        try:
            allowed, _error = await asyncio.wait_for(self._check_request_context(
                {"platform": "qq", "stream_id": session_id, "user_id": request.user_id, "group_id": ""}
            ), timeout=2)
        except Exception as exc:
            self.ctx.logger.warning(f"银白龙语音回答校验失败：{type(exc).__name__}；保留正常文字")
            return {"action": "continue"}
        if not allowed or request.consumed:
            return {"action": "continue"}
        request.consumed = True
        if len(text) > self.config.voice.max_length:
            self.ctx.logger.warning("银白龙语音回答超过朗读长度；本次保留完整文字")
            return {"action": "continue"}
        try:
            audio = await asyncio.wait_for(self._synthesize(text), timeout=self.config.voice.timeout_seconds)
            if not audio or len(audio) > 2 * 1024 * 1024:
                self.ctx.logger.warning("银白龙语音回答音频为空或过大；保留正常文字")
                return {"action": "continue"}
        except Exception as exc:
            self.ctx.logger.warning(f"银白龙语音回答合成失败：{type(exc).__name__}；保留正常文字")
            return {"action": "continue"}
        digest = sha256(audio).hexdigest()
        voice_component = {
            "type": "voice", "data": text, "hash": digest,
            "binary_data_base64": base64.b64encode(audio).decode("ascii"),
        }
        nonce = uuid4().hex
        additional_config = info.get("additional_config") or {}
        if not isinstance(additional_config, dict):
            additional_config = {}
        updated_info = {**info, "additional_config": {**additional_config, "silver_dragon_voice_delivery": nonce}}
        # NapCat 不能可靠地把 record 与图片、表情混合发送；成功语音只保留 record。
        updated_message = {
            **message,
            "raw_message": [voice_component],
            "message_info": updated_info,
            "processed_plain_text": text,
        }
        self._voice_deliveries[nonce] = monotonic() + self._VOICE_REQUEST_TTL_SECONDS
        self._prune_voice_reply_state()
        self.ctx.logger.info("银白龙已将本条正常回答转换为语音（等待发送回执）")
        return {"action": "continue", "modified_kwargs": {**kwargs, "message": updated_message}}

    @HookHandler(
        "send_service.before_send", name="voice_direct_qq_send",
        description="QQ 出站消息不显示引用，保留内部回复关联", order="late", timeout_ms=2000,
    )
    async def force_direct_qq_send(self, **kwargs: Any) -> dict[str, Any]:
        """清理可见引用组件，并保持动态语音所需的内部目标 ID。"""

        message = kwargs.get("message")
        if (
            not self.config.plugin.enabled
            or not isinstance(message, dict)
            or str(message.get("platform") or "").strip().lower() != "qq"
        ):
            return {"action": "continue"}

        raw_message = message.get("raw_message")
        updated_message = message
        if isinstance(raw_message, list):
            updated_message = {
                **message,
                "raw_message": [
                    component for component in raw_message
                    if not (isinstance(component, dict) and str(component.get("type") or "").lower() == "reply")
                ],
            }
        return {
            "action": "continue",
            "modified_kwargs": {**kwargs, "message": updated_message, "set_reply": False},
        }

    @HookHandler(
        "send_service.after_send", name="voice_delivery",
        description="仅依据宿主最终回执记录本轮语音状态", timeout_ms=2000,
    )
    async def observe_voice_delivery(self, **kwargs: Any) -> dict[str, Any]:
        """识别转换音频的最终回执，不补发、不重试。"""

        self._prune_voice_reply_state()
        message = kwargs.get("message")
        if isinstance(message, dict) and isinstance(message.get("message_info"), dict):
            additional_config = message["message_info"].get("additional_config") or {}
            if isinstance(additional_config, dict):
                nonce = str(additional_config.get("silver_dragon_voice_delivery") or "")
                if self._voice_deliveries.pop(nonce, None) is not None:
                    confirmed = kwargs.get("sent") is True
                    self.ctx.logger.info(f"银白龙动态语音回答最终回执：sent={str(confirmed).lower()}（不自动重试）")
        return {"action": "continue"}

    @staticmethod
    def _text_from_message(message: dict[str, Any]) -> str:
        """只取本条真实文字段，不把引用内容或图片描述当作用户指令。"""

        raw = message.get("raw_message")
        if not isinstance(raw, list):
            return ""
        return "".join(component["data"] for component in raw
                       if isinstance(component, dict) and component.get("type") == "text"
                       and isinstance(component.get("data"), str)).strip()

    @staticmethod
    def _normalize_reply_text(text: str) -> str:
        """仅忽略空白用于关闭引用时的已生成正文关联。"""

        return " ".join(text.split())

    def _prune_voice_reply_state(self) -> None:
        """限制短期状态数量并清除过期请求，含已消费的去重标记。"""

        now = monotonic()
        for key, item in list(self._voice_reply_requests.items()):
            if item.expires_at <= now:
                del self._voice_reply_requests[key]
        while len(self._voice_reply_requests) > self._VOICE_REQUEST_MAX_ENTRIES:
            self._voice_reply_requests.popitem(last=False)
        for key, expires_at in list(self._voice_deliveries.items()):
            if expires_at <= now:
                del self._voice_deliveries[key]
        while len(self._voice_deliveries) > self._VOICE_REQUEST_MAX_ENTRIES:
            self._voice_deliveries.popitem(last=False)
        for key, expires_at in list(self._voice_checked_targets.items()):
            if expires_at <= now:
                del self._voice_checked_targets[key]
        while len(self._voice_checked_targets) > self._VOICE_REQUEST_MAX_ENTRIES:
            self._voice_checked_targets.popitem(last=False)

    async def _is_authorized_session(self, session_id: str) -> bool:
        """用可信 Hook 会话和配置内授权用户查验真实私聊，忽略模型填写的身份。"""

        if not session_id or not self.config.plugin.enabled:
            return False
        for user_id in self.config.access.allowed_user_ids:
            allowed, _error = await self._check_request_context(
                {"platform": "qq", "stream_id": session_id, "user_id": user_id, "group_id": ""}
            )
            if allowed:
                return True
        return False

    async def _send_requested_voice(self, text: str, request: dict[str, Any]) -> tuple[bool, str]:
        """校验当前请求并合成、发送单条语音。"""

        allowed, error = await self._check_request_context(request)
        if not allowed:
            self.ctx.logger.warning("银白龙语音请求被拒绝：上下文或授权不满足条件")
            return False, error

        normalized_text = str(text or "").strip()
        if not normalized_text:
            return False, "语音内容不能为空。"
        if len(normalized_text) > self.config.voice.max_length:
            return False, f"语音内容不能超过 {self.config.voice.max_length} 个字符。"

        dedup_key = self._build_dedup_key(request, normalized_text)
        if self._is_duplicate(dedup_key):
            return False, "相同请求正在处理或刚刚已处理，请勿重复发送。"
        self._pending_requests.add(dedup_key)
        try:
            try:
                audio = await asyncio.wait_for(self._synthesize(normalized_text), timeout=self.config.voice.timeout_seconds)
            except TimeoutError:
                self.ctx.logger.warning("银白龙语音合成超时")
                return False, "语音合成超时，本次没有发送。"
            except Exception as exc:
                self.ctx.logger.warning(f"银白龙语音合成失败：{type(exc).__name__}")
                return False, "语音合成失败，本次没有发送。"

            if not audio:
                self.ctx.logger.warning("银白龙语音合成返回空音频")
                return False, "语音合成失败，本次没有发送。"

            stream_id = str(request.get("stream_id") or "").strip()
            audio_base64 = base64.b64encode(audio).decode("ascii")
            try:
                send_result = await self.ctx.send.hybrid(
                    [{"type": "voice", "content": audio_base64}], stream_id, return_details=True, set_reply=False
                )
            except Exception as exc:
                self.ctx.logger.warning(f"银白龙语音发送调用异常：{type(exc).__name__}；不自动重试")
                return False, "语音发送失败，发送状态不明，本次不会自动重试。"

            if not self._send_succeeded(send_result):
                self.ctx.logger.warning("银白龙语音发送失败或状态不明；不自动重试")
                return False, "语音发送失败，发送状态不明，本次不会自动重试。"
            return True, "已发送语音。"
        finally:
            self._pending_requests.discard(dedup_key)
            self._remember_request(dedup_key)

    async def _synthesize(self, text: str) -> bytes:
        """使用配置的 Edge TTS 参数收集 MP3 音频字节。"""

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.config.voice.voice,
            rate=self.config.voice.rate,
            pitch=self.config.voice.pitch,
        )
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data")
                if isinstance(data, bytes):
                    chunks.append(data)
        return b"".join(chunks)

    async def _check_request_context(self, request: dict[str, Any]) -> tuple[bool, str]:
        """仅接受与宿主当前聊天流一致的 QQ 私聊授权请求者。"""

        if not self.config.plugin.enabled:
            return False, "语音插件尚未启用。"
        platform = str(request.get("platform") or "").strip().lower()
        group_id = str(request.get("group_id") or "").strip()
        stream_id = str(request.get("stream_id") or "").strip()
        user_id = str(request.get("user_id") or "").strip()
        allowed_users = {str(value).strip() for value in self.config.access.allowed_user_ids if str(value).strip()}
        if platform != "qq" or group_id or not stream_id or not user_id:
            return False, "仅支持当前 QQ 私聊请求。"
        if not allowed_users or user_id not in allowed_users:
            return False, "当前请求者未获授权使用语音。"

        try:
            # SDK 2.8.1 已解包宿主的 {success, stream}，这里直接接收 stream 本体。
            resolved_stream = await self.ctx.chat.get_stream_by_user_id(user_id=user_id, platform="qq")
        except Exception as exc:
            self.ctx.logger.warning(f"银白龙语音无法核验当前私聊流：{type(exc).__name__}")
            return False, "无法核验当前 QQ 私聊，本次没有发送。"

        if not isinstance(resolved_stream, dict) or not resolved_stream.get("stream_id"):
            self.ctx.logger.warning("银白龙语音无法核验当前私聊流：查询未返回会话")
            return False, "无法核验当前 QQ 私聊，本次没有发送。"
        if not self._stream_matches_request(resolved_stream, request):
            self.ctx.logger.warning("银白龙语音私聊流核验不匹配")
            return False, "仅支持当前 QQ 私聊请求。"
        return True, ""

    @staticmethod
    def _stream_matches_request(resolved_stream: Any, request: dict[str, Any]) -> bool:
        """核对 SDK 返回的真实会话；不接受原始 RPC 包装或缺失身份字段。"""

        if not isinstance(resolved_stream, dict):
            return False
        stream_id = str(request.get("stream_id") or "").strip()
        user_id = str(request.get("user_id") or "").strip()
        resolved_stream_id = str(resolved_stream.get("stream_id") or "").strip()
        resolved_platform = str(resolved_stream.get("platform") or "").strip().lower()
        resolved_user_id = str(resolved_stream.get("user_id") or "").strip()
        resolved_group_id = str(resolved_stream.get("group_id") or "").strip()
        is_group = bool(resolved_stream.get("is_group_session", False))
        chat_type = str(resolved_stream.get("chat_type") or "").strip().lower()
        return bool(
            stream_id and user_id
            and resolved_stream_id == stream_id
            and resolved_platform == "qq"
            and resolved_user_id == user_id
            and not resolved_group_id and not is_group
            and chat_type == "private"
        )

    @staticmethod
    def _send_succeeded(send_result: Any) -> bool:
        """仅在宿主明确确认已发送时报告成功。"""

        if isinstance(send_result, dict):
            return bool(send_result.get("sent", False))
        return bool(send_result)

    def _build_dedup_key(self, request: dict[str, Any], text: str) -> str:
        """优先用宿主消息 ID 去重，缺失时使用聊天流和内容的短时指纹。"""

        message = request.get("message")
        if isinstance(message, dict):
            message_id = str(message.get("message_id") or "").strip()
            if message_id:
                return f"message:{message_id}"
        stream_id = str(request.get("stream_id") or "").strip()
        digest = sha256(text.encode("utf-8")).hexdigest()[:16]
        return f"stream:{stream_id}:text:{digest}"

    def _is_duplicate(self, key: str) -> bool:
        """清理过期记录并检查重复请求。"""

        now = monotonic()
        while self._recent_requests:
            oldest_key, oldest_at = next(iter(self._recent_requests.items()))
            if now - oldest_at <= self._DEDUP_WINDOW_SECONDS:
                break
            self._recent_requests.pop(oldest_key)
        return key in self._pending_requests or key in self._recent_requests

    def _remember_request(self, key: str) -> None:
        """在处理结束后记录冷却时间，防止失败后的自动重复发送。"""

        self._recent_requests[key] = monotonic()
        self._recent_requests.move_to_end(key)
        while len(self._recent_requests) > self._DEDUP_MAX_ENTRIES:
            self._recent_requests.popitem(last=False)

    async def _send_command_error(self, message: str, stream_id: str) -> None:
        """命令失败时在当前聊天流给出简短反馈。"""

        if stream_id:
            await self.ctx.send.text(message, stream_id, set_reply=False)


def create_plugin() -> SilverDragonVoicePlugin:
    """创建插件实例。"""

    return SilverDragonVoicePlugin()
