"""NapCat 通知文本渲染器。"""

from __future__ import annotations

from typing import Any, Mapping


class NapCatNoticeTextRenderer:
    """根据通知载荷生成可读文本。"""

    def build_notice_text(self, payload: Mapping[str, Any], actor_name: str) -> str:
        """根据 NapCat 通知事件生成可读文本。

        Args:
            payload: 原始通知事件。
            actor_name: 事件操作者显示名。

        Returns:
            str: 生成的可读通知文本。
        """
        notice_type = str(payload.get("notice_type") or "").strip()
        sub_type = str(payload.get("sub_type") or "").strip()
        target_id = str(payload.get("target_id") or "").strip()
        target_user_id = str(payload.get("user_id") or "").strip()
        is_natural_lift = bool(payload.get("is_natural_lift", False))

        if notice_type in {"group_recall", "friend_recall"}:
            return f"{actor_name} 撤回了一条消息"
        if notice_type == "notify" and sub_type == "poke":
            target_text = f" -> {target_id}" if target_id else ""
            return f"{actor_name} 发起了戳一戳{target_text}"
        if notice_type == "notify" and sub_type == "group_name":
            return f"{actor_name} 修改了群名称"
        if notice_type == "group_ban" and sub_type == "ban":
            duration = payload.get("duration")
            if target_user_id in {"", "0"}:
                return f"{actor_name} 开启了全体禁言"
            return f"{actor_name} 禁言了用户 {target_user_id}，时长 {duration} 秒"
        if notice_type == "group_ban" and sub_type == "whole_lift_ban":
            if is_natural_lift:
                return "群全体禁言已自然解除"
            return f"{actor_name} 解除了全体禁言"
        if notice_type == "group_ban" and sub_type == "lift_ban":
            if is_natural_lift:
                return f"用户 {target_user_id} 的禁言已自然解除"
            return f"{actor_name} 解除了用户 {target_user_id} 的禁言"
        if notice_type == "group_upload":
            file_info = payload.get("file", {})
            file_name = ""
            if isinstance(file_info, Mapping):
                file_name = str(file_info.get("name") or "").strip()
            return f"{actor_name} 上传了文件{f'：{file_name}' if file_name else ''}"
        if notice_type == "group_increase":
            return f"{actor_name} 加入了群聊"
        if notice_type == "group_decrease":
            return f"{actor_name} 离开了群聊"
        if notice_type == "group_admin":
            return f"{actor_name} 的群管理员状态发生变化"
        if notice_type == "essence":
            return f"{actor_name} 触发了精华消息事件"
        if notice_type == "group_msg_emoji_like":
            return f"{actor_name} 给一条消息添加了表情回应"
        return f"[notice] {notice_type}.{sub_type}".strip(".")
