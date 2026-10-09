"""NapCat 通知事件资料补全器。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...services import NapCatQueryService
from .helpers import normalize_optional_string


class NapCatNoticeEntityResolver:
    """为通知事件补全用户和群资料。"""

    def __init__(self, query_service: NapCatQueryService) -> None:
        """初始化实体补全器。

        Args:
            query_service: NapCat 查询服务。
        """
        self._query_service = query_service

    async def build_user_info(self, group_id: str, user_id: str) -> Dict[str, Optional[str]]:
        """构造通知消息的用户信息。

        Args:
            group_id: 群号；私聊或系统通知时为空字符串。
            user_id: 事件关联用户号。

        Returns:
            Dict[str, Optional[str]]: 规范化后的用户信息字典。
        """
        if not user_id:
            return {
                "user_id": "notice",
                "user_nickname": "系统通知",
                "user_cardname": None,
            }

        member_info: Optional[Dict[str, Any]]
        if group_id:
            member_info = await self._query_service.get_group_member_info(group_id, user_id)
        else:
            member_info = await self._query_service.get_stranger_info(user_id)

        if member_info is None:
            return {
                "user_id": user_id,
                "user_nickname": user_id,
                "user_cardname": None,
            }

        return {
            "user_id": user_id,
            "user_nickname": str(member_info.get("nickname") or user_id),
            "user_cardname": normalize_optional_string(member_info.get("card")),
        }

    async def build_group_info(self, group_id: str) -> Optional[Dict[str, str]]:
        """构造通知消息的群信息。

        Args:
            group_id: 群号。

        Returns:
            Optional[Dict[str, str]]: 群信息字典；若不是群通知则返回 ``None``。
        """
        if not group_id:
            return None

        group_info = await self._query_service.get_group_info(group_id)
        group_name = str(group_info.get("group_name") or f"group_{group_id}") if group_info else f"group_{group_id}"
        return {"group_id": group_id, "group_name": group_name}
