"""Maisaka 内置工具执行上下文。"""

from __future__ import annotations

from base64 import b64decode
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from src.chat.utils.qq_text_format import format_qq_text
from src.chat.utils.utils import ProcessedResponseSegment, process_llm_response, process_llm_response_segments
from src.common.data_models.message_component_data_model import (
    AtComponent,
    EmojiComponent,
    ImageComponent,
    MessageSequence,
    TextComponent,
)
from src.common.logger import get_logger
from src.config.config import global_config
from src.core.tooling import ToolExecutionResult
from src.maisaka.context.message_adapter import format_speaker_content
from src.maisaka.context.messages import SessionBackedMessage
from src.maisaka.context.planner_messages import (
    build_planner_prefix,
    build_session_backed_text_message,
    extract_quote_ids_from_message_sequence,
)
from src.plugin_runtime.integration import get_plugin_runtime_manager

if TYPE_CHECKING:
    from src.maisaka.reasoning_engine import MaisakaReasoningEngine
    from src.maisaka.runtime import MaisakaHeartFlowChatting

logger = get_logger("maisaka_builtin_context")


@dataclass
class PostProcessedReplyMessage:
    """一条待发送的后处理回复及其引用提示。"""

    sequence: MessageSequence
    quote_previous: bool = False


@dataclass
class PreparedReplyAttachments:
    """生成正文前已核对的附件，发送时复用同一份图片字节。"""

    at_components: List[AtComponent] = field(default_factory=list)
    image_components: List[ImageComponent | EmojiComponent] = field(default_factory=list)
    emoji_components: List[EmojiComponent] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    diagnostics: List[str] = field(default_factory=list)

    def prompt_snapshot(self) -> Dict[str, Any]:
        """只提供真实已准备附件的信息，不把期望描述当作实际选图。"""

        return {
            "pictures": [component.content for component in self.image_components],
            "emojis": [component.content for component in self.emoji_components],
            "at_count": len(self.at_components),
            "errors": list(self.errors),
        }


class EmojiMatchUnavailable(ValueError):
    """表情请求没有符合角色、情绪和格式要求的可发送匹配。"""


class BuiltinToolRuntimeContext:
    """为拆分后的内置工具提供统一运行时能力。"""

    def __init__(
        self,
        engine: "MaisakaReasoningEngine",
        runtime: "MaisakaHeartFlowChatting",
    ) -> None:
        self.engine = engine
        self.runtime = runtime

    @staticmethod
    def build_success_result(
        tool_name: str,
        content: str = "",
        structured_content: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        post_history_messages: Optional[Sequence[Any]] = None,
    ) -> ToolExecutionResult:
        """构造统一工具成功结果。"""

        return ToolExecutionResult(
            tool_name=tool_name,
            success=True,
            content=content,
            structured_content=structured_content,
            post_history_messages=list(post_history_messages or []),
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def build_failure_result(
        tool_name: str,
        error_message: str,
        structured_content: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """构造统一工具失败结果。"""

        return ToolExecutionResult(
            tool_name=tool_name,
            success=False,
            error_message=error_message,
            structured_content=structured_content,
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def normalize_words(raw_words: Any) -> List[str]:
        """清洗黑话查询词条列表。"""

        if not isinstance(raw_words, list):
            return []

        normalized_words: List[str] = []
        seen_words: set[str] = set()
        for item in raw_words:
            if not isinstance(item, str):
                continue
            word = item.strip()
            if not word or word in seen_words:
                continue
            seen_words.add(word)
            normalized_words.append(word)
        return normalized_words

    @staticmethod
    def normalize_jargon_query_results(raw_results: Any) -> List[Dict[str, object]]:
        """规范化黑话查询结果列表。"""

        if not isinstance(raw_results, list):
            return []

        normalized_results: List[Dict[str, object]] = []
        for raw_item in raw_results:
            if not isinstance(raw_item, dict):
                continue
            word = str(raw_item.get("word") or "").strip()
            matches = raw_item.get("matches")
            normalized_matches: List[Dict[str, str]] = []
            if isinstance(matches, list):
                for match in matches:
                    if not isinstance(match, dict):
                        continue
                    content = str(match.get("content") or "").strip()
                    meaning = str(match.get("meaning") or "").strip()
                    if not content or not meaning:
                        continue
                    normalized_matches.append({"content": content, "meaning": meaning})

            normalized_results.append(
                {
                    "word": word,
                    "found": bool(raw_item.get("found", bool(normalized_matches))),
                    "matches": normalized_matches,
                }
            )
        return normalized_results

    @staticmethod
    def post_process_reply_text(
        reply_text: str,
        *,
        skip_post_process: bool = False,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> List[str]:
        """沿用旧回复链的文本后处理，执行分段与错别字注入。"""

        if skip_post_process:
            return [reply_text]

        processed_segments: List[str] = []
        for segment in process_llm_response(
            reply_text,
            enable_splitter=enable_splitter,
            enable_chinese_typo=enable_chinese_typo,
        ):
            if segment.strip():
                processed_segments.append(segment)

        if processed_segments:
            return processed_segments
        return [reply_text.strip()]

    @staticmethod
    def post_process_reply_segments(
        reply_text: str,
        *,
        skip_post_process: bool = False,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> List[ProcessedResponseSegment]:
        """执行文本后处理，并保留错别字纠正段的引用提示。"""

        if skip_post_process:
            return [ProcessedResponseSegment(reply_text.strip())]

        processed_segments: List[ProcessedResponseSegment] = []
        for segment in process_llm_response_segments(
            reply_text,
            enable_splitter=enable_splitter,
            enable_chinese_typo=enable_chinese_typo,
        ):
            if segment.text.strip():
                processed_segments.append(
                    ProcessedResponseSegment(
                        segment.text,
                        quote_previous=segment.quote_previous,
                    )
                )

        if processed_segments:
            return processed_segments
        return [ProcessedResponseSegment(reply_text.strip())]

    async def post_process_reply_message_items_async(
        self,
        reply_text: str,
        *,
        skip_post_process: bool = False,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> List[PostProcessedReplyMessage]:
        """将 replyer 输出处理为带发送提示的组件序列。"""

        return self.post_process_reply_message_items(
            reply_text,
            skip_post_process=skip_post_process,
            enable_splitter=enable_splitter,
            enable_chinese_typo=enable_chinese_typo,
        )

    def post_process_reply_message_items(
        self,
        reply_text: str,
        *,
        skip_post_process: bool = False,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> List[PostProcessedReplyMessage]:
        """将纯文本回复处理为带发送提示的组件序列。"""

        # QQ 普通消息不解析数学或 Markdown；在分段前转换，避免拆开公式标记。
        # 显式跳过后处理的语音等插件仍使用原文，保持其正文授权匹配。
        runtime = getattr(self, "runtime", None)
        stream = getattr(runtime, "chat_stream", None)
        if not skip_post_process and stream is not None and stream.platform == "qq":
            formatted_text = format_qq_text(reply_text)
            if formatted_text != reply_text:
                enable_chinese_typo = False
            reply_text = formatted_text

        return [
            PostProcessedReplyMessage(
                sequence=MessageSequence([TextComponent(segment.text)]),
                quote_previous=segment.quote_previous,
            )
            for segment in self.post_process_reply_segments(
                reply_text,
                skip_post_process=skip_post_process,
                enable_splitter=enable_splitter,
                enable_chinese_typo=enable_chinese_typo,
            )
        ]

    async def post_process_reply_message_sequences_async(
        self,
        reply_text: str,
        *,
        skip_post_process: bool = False,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> List[MessageSequence]:
        """将 replyer 输出处理为可发送组件序列。"""

        return self.post_process_reply_message_sequences(
            reply_text,
            skip_post_process=skip_post_process,
            enable_splitter=enable_splitter,
            enable_chinese_typo=enable_chinese_typo,
        )

    def post_process_reply_message_sequences(
        self,
        reply_text: str,
        *,
        skip_post_process: bool = False,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> List[MessageSequence]:
        """将纯文本回复处理为可发送组件序列。"""

        return [
            item.sequence
            for item in self.post_process_reply_message_items(
                reply_text,
                skip_post_process=skip_post_process,
                enable_splitter=enable_splitter,
                enable_chinese_typo=enable_chinese_typo,
            )
        ]

    def _resolve_at_attachment(self, raw_target: Any) -> AtComponent:
        """把 attach_at 参数解析为对目标消息发送者的 at 组件。"""

        if isinstance(raw_target, dict):
            target_user_id = str(raw_target.get("user_id") or "").strip()
            target_message_id = str(raw_target.get("msg_id") or raw_target.get("message_id") or "").strip()
        else:
            target_user_id = ""
            target_message_id = str(raw_target or "").strip()

        if target_user_id:
            return AtComponent(target_user_id=target_user_id)

        target_message = self.runtime.find_source_message_by_id(target_message_id)
        if target_message is None:
            raise ValueError(f"无法解析 at 目标消息：msg_id={target_message_id}")

        user_info = target_message.message_info.user_info
        return AtComponent(
            target_user_id=user_info.user_id,
            target_user_nickname=user_info.user_nickname,
            target_user_cardname=user_info.user_cardname,
        )

    async def _resolve_image_attachment(self, raw_attachment: Any) -> ImageComponent | EmojiComponent:
        """把 attach_pic 参数按 send_image 的 msg_id/index 语义解析为图片组件。"""

        from .send_image import _collect_message_images

        if isinstance(raw_attachment, dict):
            target_message_id = str(
                raw_attachment.get("media_index")
                or raw_attachment.get("msg_id")
                or raw_attachment.get("message_id")
                or raw_attachment.get("source")
                or ""
            ).strip()
            raw_index = raw_attachment.get("index", raw_attachment.get("image_index", 0))
        else:
            target_message_id = str(raw_attachment or "").strip()
            raw_index = 0

        try:
            image_index = int(raw_index or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"图片序号无效：index={raw_index}") from exc

        images, error = await _collect_message_images(self, target_message_id)
        if error is not None:
            raise ValueError(error)
        if image_index < 0 or image_index >= len(images):
            raise ValueError(f"图片序号超出范围：index={image_index}，该消息共有 {len(images)} 张图片。")

        image = images[image_index]
        component_type = EmojiComponent if isinstance(image, EmojiComponent) else ImageComponent
        return component_type(
            binary_hash=image.binary_hash,
            content=image.content,
            binary_data=image.binary_data,
        )

    async def _resolve_emoji_attachment(self, raw_emotion: Any) -> EmojiComponent:
        """把 attach_emoji 参数解析为表情包组件。"""

        from src.common.utils.image_path import resolve_stored_image_path
        from src.emoji_system.emoji_identity import lookup_character_emoji
        from src.emoji_system.emoji_manager import emoji_manager

        requested_emotion = str(raw_emotion or "").strip()
        selected_emoji = await emoji_manager.get_emoji_for_emotion(requested_emotion)
        if selected_emoji is None:
            raise EmojiMatchUnavailable("当前表情库没有符合所请求角色、情绪或动图格式的表情。")

        emoji_path = resolve_stored_image_path(selected_emoji.full_path)
        emoji_bytes = emoji_path.read_bytes()
        character_emoji = lookup_character_emoji(selected_emoji.file_hash)
        description = (
            character_emoji.description if character_emoji is not None
            else "其他表情；以下只是情绪标签，不能据此确认人物外观或身份：" + selected_emoji.description.strip()
        )
        return EmojiComponent(
            binary_hash=selected_emoji.file_hash,
            content=description,
            binary_data=emoji_bytes,
        )

    @staticmethod
    def record_sent_reply_emoji_usage(sequence: MessageSequence) -> None:
        """只在对应消息实际发送成功后记账，预选或生成失败不算使用。"""

        sent_hashes = {component.binary_hash for component in sequence.components if isinstance(component, EmojiComponent)}
        if not sent_hashes:
            return
        from src.emoji_system.emoji_manager import emoji_manager

        for emoji in emoji_manager.emojis:
            if emoji.file_hash in sent_hashes:
                emoji_manager.update_emoji_usage(emoji)

    @staticmethod
    def _normalize_attachment_list(raw_value: Any, argument_name: str) -> List[Any]:
        """将可重复附件参数规范化为列表。"""

        if raw_value is None or raw_value == "":
            return []
        if isinstance(raw_value, list):
            return raw_value
        if isinstance(raw_value, (str, dict)):
            return [raw_value]
        raise ValueError(f"{argument_name} 参数类型无效，应为字符串、对象或列表。")

    async def prepare_rich_reply_attachments_async(
        self, attachments: Optional[Dict[str, Any]] = None,
    ) -> PreparedReplyAttachments:
        """提前选图并读取原始字节；失败显式记录，让正文准确解释附件缺失。"""

        attachment_args = dict(attachments or {})
        prepared = PreparedReplyAttachments()
        for raw_target in self._normalize_attachment_list(attachment_args.get("attach_at"), "attach_at"):
            try:
                prepared.at_components.append(self._resolve_at_attachment(raw_target))
            except Exception as exc:
                logger.exception(f"{self.runtime.log_prefix} 准备 at 附件失败: {exc}")
                prepared.errors.append("无法确定本次要提醒的人。")
                prepared.diagnostics.append("at 附件：" + str(exc))
        for raw_image in self._normalize_attachment_list(attachment_args.get("attach_pic"), "attach_pic"):
            try:
                prepared.image_components.append(await self._resolve_image_attachment(raw_image))
            except Exception as exc:
                logger.exception(f"{self.runtime.log_prefix} 准备图片附件失败: {exc}")
                prepared.errors.append("引用的图片或动图暂时无法读取。")
                prepared.diagnostics.append("图片附件：" + str(exc))
        raw_emoji = attachment_args.get("attach_emoji")
        if str(raw_emoji or "").strip():
            try:
                prepared.emoji_components.append(await self._resolve_emoji_attachment(raw_emoji))
            except Exception as exc:
                logger.exception(f"{self.runtime.log_prefix} 准备表情附件失败: {exc}")
                prepared.errors.append(
                    str(exc) if isinstance(exc, EmojiMatchUnavailable)
                    else "选中的表情暂时无法读取或核对。"
                )
                prepared.diagnostics.append("表情附件：" + str(exc))
        return prepared

    async def post_process_rich_reply_message_sequences_async(
        self,
        reply_text: str,
        attachments: Optional[Dict[str, Any]] = None,
        *,
        skip_post_process: bool = False,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
    ) -> List[MessageSequence]:
        """将 replyer 正文和 reply 动作附件参数处理为可发送组件序列。"""

        items = await self.post_process_rich_reply_message_items_async(
            reply_text,
            attachments,
            skip_post_process=skip_post_process,
            enable_splitter=enable_splitter,
            enable_chinese_typo=enable_chinese_typo,
        )
        return [item.sequence for item in items]

    async def post_process_rich_reply_message_items_async(
        self,
        reply_text: str,
        attachments: Optional[Dict[str, Any]] = None,
        *,
        skip_post_process: bool = False,
        enable_splitter: bool = True,
        enable_chinese_typo: bool = True,
        prepared_attachments: Optional[PreparedReplyAttachments] = None,
    ) -> List[PostProcessedReplyMessage]:
        """处理 replyer 正文和附件，并保留每条消息的发送提示。"""

        items = self.post_process_reply_message_items(
            reply_text,
            skip_post_process=skip_post_process,
            enable_splitter=enable_splitter,
            enable_chinese_typo=enable_chinese_typo,
        )
        prepared = prepared_attachments
        if prepared is None:
            prepared = await self.prepare_rich_reply_attachments_async(attachments)
        at_components = prepared.at_components
        image_components = prepared.image_components
        emoji_components = prepared.emoji_components

        if not at_components and not image_components and not emoji_components:
            return items

        at_prefix_components = []
        for at_component in at_components:
            at_prefix_components.extend([at_component, TextComponent(" ")])

        items[0].sequence.components = at_prefix_components + items[0].sequence.components
        items[-1].sequence.components.extend(image_components)
        items[-1].sequence.components.extend(emoji_components)
        return items

    def get_runtime_manager(self) -> Any:
        """获取插件运行时管理器。"""

        return get_plugin_runtime_manager()

    def _should_include_planner_chat_id(self) -> bool:
        """当前上下文写入规划器历史时是否需要保留聊天流 ID。"""

        return self.runtime._is_focus_mode_active_for_current_chat()

    def append_guided_reply_to_chat_history(self, reply_text: str) -> None:
        """将引导回复写回 Maisaka 历史。"""

        bot_name = global_config.bot.nickname.strip() or "MaiSaka"
        reply_timestamp = datetime.now()
        include_chat_id = self._should_include_planner_chat_id()
        history_message = build_session_backed_text_message(
            speaker_name=bot_name,
            text=reply_text,
            timestamp=reply_timestamp,
            source_kind="guided_reply",
            chat_id=self.runtime.session_id,
            include_chat_id=include_chat_id,
            is_self_message=True,
        )
        self.runtime._chat_history.append(history_message)

    def append_sent_message_to_chat_history(self, message: Any, *, source_kind: str = "guided_reply") -> bool:
        """将已发送消息写回 Maisaka 历史。"""

        runtime_append = getattr(self.runtime, "append_sent_message_to_chat_history", None)
        if callable(runtime_append):
            return bool(runtime_append(message, source_kind=source_kind))

        from src.maisaka.context.messages import SessionBackedMessage
        from src.maisaka.context.history import build_prefixed_message_sequence, build_session_message_visible_text
        user_info = message.message_info.user_info
        speaker_name = user_info.user_cardname or user_info.user_nickname or user_info.user_id
        include_chat_id = self._should_include_planner_chat_id()
        planner_prefix = build_planner_prefix(
            timestamp=message.timestamp,
            user_name=speaker_name,
            group_card=user_info.user_cardname or "",
            message_id=message.message_id,
            chat_id=message.session_id,
            quote_ids=extract_quote_ids_from_message_sequence(message.raw_message),
            include_message_id=not message.is_notify and bool(message.message_id),
            include_chat_id=include_chat_id,
            is_self_message=source_kind == "guided_reply",
        )
        history_message = SessionBackedMessage.from_session_message(
            message,
            raw_message=build_prefixed_message_sequence(message.raw_message, planner_prefix),
            visible_text=build_session_message_visible_text(
                message,
                include_reply_components=source_kind != "guided_reply",
            ),
            source_kind=source_kind,
        )
        self.runtime._chat_history.append(history_message)
        return True

    def append_sent_emoji_to_chat_history(
        self,
        *,
        emoji_base64: str,
        success_message: str,
    ) -> None:
        """将 bot 主动发送的表情包同步到 Maisaka 历史。"""

        bot_name = global_config.bot.nickname.strip() or "MaiSaka"
        reply_timestamp = datetime.now()
        include_chat_id = self._should_include_planner_chat_id()
        planner_prefix = build_planner_prefix(
            timestamp=reply_timestamp,
            user_name=bot_name,
            chat_id=self.runtime.session_id,
            include_chat_id=include_chat_id,
            is_self_message=True,
        )
        history_message = SessionBackedMessage(
            raw_message=MessageSequence(
                [
                    TextComponent(planner_prefix),
                    EmojiComponent(
                        binary_hash="",
                        content=success_message,
                        binary_data=b64decode(emoji_base64),
                    ),
                ]
            ),
            visible_text=format_speaker_content(
                bot_name,
                "[表情包]",
                reply_timestamp,
            ),
            timestamp=reply_timestamp,
            source_kind="guided_reply",
        )
        self.runtime._chat_history.append(history_message)
