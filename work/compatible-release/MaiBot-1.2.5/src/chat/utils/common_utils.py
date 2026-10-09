from typing import Optional

from src.common.logger import get_logger
from src.common.utils.utils_config import ChatConfigUtils, ExpressionConfigUtils

logger = get_logger("common_utils")


class TempMethodsExpression:
    """用于临时存放一些方法的类"""

    @staticmethod
    def _find_expression_config_item(chat_stream_id: Optional[str] = None):
        return ExpressionConfigUtils._find_expression_config_item(chat_stream_id)

    @staticmethod
    def get_expression_config_for_chat(chat_stream_id: Optional[str] = None) -> tuple[bool, bool]:
        """
        根据聊天流 ID 获取表达配置。

        Args:
            chat_stream_id: 聊天流 ID，格式为哈希值

        Returns:
            tuple: (是否使用表达, 是否学习表达)
        """
        return ExpressionConfigUtils.get_expression_config_for_chat(chat_stream_id)

    @staticmethod
    def _get_stream_id(
        platform: str,
        id_str: str,
        is_group: bool = False,
    ) -> Optional[str]:
        """
        根据平台、ID 字符串和是否为群聊解析已存在的聊天流 ID。

        注意：业务模块不应自行计算 session_id，这里只返回已存在的真实聊天流。
        """
        chat_type = "group" if is_group else "private"
        session_ids = ChatConfigUtils.resolve_existing_session_ids(platform, id_str, chat_type)
        return next(iter(session_ids), None)
