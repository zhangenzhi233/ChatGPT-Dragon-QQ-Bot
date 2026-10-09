"""回复效果记录中的引用消息辅助工具。"""

from typing import Any

from src.common.data_models.message_component_data_model import MessageSequence, ReplyComponent


def extract_quote_target_ids(message_sequence: MessageSequence | None) -> list[str]:
    """从消息片段中提取引用回复目标消息 ID。"""

    if message_sequence is None:
        return []

    target_ids: list[str] = []
    for component in getattr(message_sequence, "components", []):
        if not isinstance(component, ReplyComponent):
            continue
        target_message_id = str(component.target_message_id or "").strip()
        if target_message_id:
            target_ids.append(target_message_id)
    return target_ids


def message_id_from_context_message(message: Any) -> str:
    """尽量从 Maisaka 上下文消息中取真实消息 ID。"""

    message_id = str(getattr(message, "message_id", "") or "").strip()
    if message_id:
        return message_id

    original_message = getattr(message, "original_message", None)
    return str(getattr(original_message, "message_id", "") or "").strip()
