"""NapCat 出站消息编解码。"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from .segment_encoder import NapCatOutboundSegmentEncoder


class NapCatOutboundCodec:
    """NapCat 出站消息编码器。"""

    def __init__(self) -> None:
        """初始化出站消息编码器。"""
        self._segment_encoder = NapCatOutboundSegmentEncoder()

    def build_outbound_action(
        self,
        message: Mapping[str, Any],
        route: Mapping[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        """为 Host 出站消息构造 OneBot 动作。

        Args:
            message: Host 侧标准 ``MessageDict``。
            route: Platform IO 路由信息。

        Returns:
            Tuple[str, Dict[str, Any]]: 动作名称与参数字典。

        Raises:
            ValueError: 当私聊出站缺少目标用户 ID 时抛出。
        """
        message_info = message.get("message_info", {})
        if not isinstance(message_info, Mapping):
            message_info = {}

        group_info = message_info.get("group_info", {})
        if not isinstance(group_info, Mapping):
            group_info = {}

        additional_config = message_info.get("additional_config", {})
        if not isinstance(additional_config, Mapping):
            additional_config = {}

        raw_message = message.get("raw_message", [])
        segments = self._segment_encoder.convert_segments(raw_message)
        is_forward_message = self._contains_forward_segment(raw_message)

        if target_group_id := str(
            group_info.get("group_id") or additional_config.get("platform_io_target_group_id") or ""
        ).strip():
            if is_forward_message:
                forward_segments = self._build_forward_message_segments(raw_message, additional_config)
                return "send_group_forward_msg", {"group_id": target_group_id, "message": forward_segments}
            return "send_group_msg", {"group_id": target_group_id, "message": segments}

        target_user_id = str(
            additional_config.get("platform_io_target_user_id")
            or additional_config.get("target_user_id")
            or route.get("target_user_id")
            or ""
        ).strip()
        if not target_user_id:
            raise ValueError("Outbound private message is missing target_user_id")

        if is_forward_message:
            forward_segments = self._build_forward_message_segments(raw_message, additional_config)
            return "send_private_forward_msg", {"message": forward_segments, "user_id": target_user_id}
        return "send_private_msg", {"message": segments, "user_id": target_user_id}

    @staticmethod
    def _contains_forward_segment(raw_message: Any) -> bool:
        """判断 Host 消息中是否包含合并转发组件。"""
        if not isinstance(raw_message, list):
            return False
        return any(isinstance(item, Mapping) and item.get("type") == "forward" for item in raw_message)

    def _build_forward_message_segments(
        self,
        raw_message: Any,
        additional_config: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        """构造 NapCat 合并转发动作需要的节点列表。"""
        if not isinstance(raw_message, list):
            return []

        forward_segments: List[Dict[str, Any]] = []
        regular_segments: List[Mapping[str, Any]] = []
        for item in raw_message:
            if not isinstance(item, Mapping):
                continue

            if item.get("type") == "forward":
                if regular_segments:
                    forward_segments.append(self._build_regular_forward_node(regular_segments, additional_config))
                    regular_segments = []
                forward_segments.extend(self._segment_encoder.convert_segments([item]))
                continue

            regular_segments.append(item)

        if regular_segments:
            forward_segments.append(self._build_regular_forward_node(regular_segments, additional_config))

        return forward_segments

    def _build_regular_forward_node(
        self,
        regular_segments: List[Mapping[str, Any]],
        additional_config: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """将合并转发消息中夹带的普通消息段包装成一个转发节点。"""
        self_id = str(additional_config.get("self_id") or "").strip()
        return {
            "type": "node",
            "data": {
                "name": "MaiBot",
                "uin": self_id,
                "content": self._segment_encoder.convert_segments(regular_segments),
            },
        }
