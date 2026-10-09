"""NapCat 官方机器人消息拦截服务。"""

from __future__ import annotations

from typing import Any, Dict

from .query_service import NapCatQueryService


class NapCatOfficialBotGuard:
    """根据群成员资料判断是否应拦截 QQ 官方机器人消息。"""

    def __init__(self, logger: Any, query_service: NapCatQueryService) -> None:
        """初始化官方机器人拦截服务。

        Args:
            logger: 插件日志对象。
            query_service: NapCat 查询服务。
        """
        self._logger = logger
        self._query_service = query_service
        self._cache: Dict[str, bool] = {}

    def clear_cache(self) -> None:
        """清空机器人识别缓存。"""
        self._cache.clear()

    async def should_reject(self, sender_user_id: str, group_id: str, ban_qq_bot: bool) -> bool:
        """判断是否应拦截当前消息。

        Args:
            sender_user_id: 发送者用户号。
            group_id: 群号。
            ban_qq_bot: 是否启用官方机器人拦截。

        Returns:
            bool: 若应拦截，则返回 ``True``。
        """
        if not ban_qq_bot or not group_id:
            return False

        cache_key = f"{group_id}:{sender_user_id}"
        cached_result = self._cache.get(cache_key)
        if cached_result is not None:
            if cached_result:
                self._logger.warning("QQ 官方机器人消息拦截已启用，消息被丢弃")
            return cached_result

        member_info = await self._query_service.get_group_member_info(group_id, sender_user_id, no_cache=True)
        if member_info is None:
            self._logger.warning("无法获取用户是否为机器人，默认放行当前消息")
            self._cache[cache_key] = False
            return False

        should_reject = bool(member_info.get("is_robot"))
        self._cache[cache_key] = should_reject
        if should_reject:
            self._logger.warning("QQ 官方机器人消息拦截已启用，消息被丢弃")
        return should_reject
