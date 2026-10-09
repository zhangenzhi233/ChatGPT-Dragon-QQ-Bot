from typing import TYPE_CHECKING, Optional

import asyncio

from src.common.database.database import get_db_session
from src.common.logger import get_logger
from src.common.message_server.api import get_global_api
from src.common.utils.math_utils import calculate_typing_time
from src.common.utils.utils_message import MessageUtils
from src.common.data_models.message_component_data_model import ReplyComponent

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage

logger = get_logger("sender")


class UniversalMessageSender:
    @staticmethod
    async def send_message(
        message: "SessionMessage",
        *,
        typing: bool = False,
        storage_message: bool = True,
        reply_message_id: Optional[str] = None,
        show_log: bool = True,
    ) -> bool:
        """
        处理、发送并存储一条消息。

        参数：
            message: SessionMessage 对象，待发送的消息。
            typing: 是否模拟打字等待。
            storage_message: 是否存储消息到数据库。
            reply_message_id: 回复消息的 ID。
            show_log: 是否显示日志。

        返回：
            bool: 消息是否发送成功。
        """
        if not message.message_id:
            logger.error("消息缺少 message_id，无法发送")
            raise ValueError("消息缺少 message_id，无法发送")

        # 设置回复
        if reply_message_id:
            message.raw_message.components.insert(0, ReplyComponent(reply_message_id))

        # 处理消息
        await message.process()

        # 模拟打字等待
        if typing:
            typing_time = calculate_typing_time(message.processed_plain_text or "")
            await asyncio.sleep(typing_time)

        # 广播消息到插件
        await UniversalMessageSender._broadcast_message_to_plugins(message)

        # 发送消息
        sent_result = await UniversalMessageSender._send_message_via_maim_message(message, show_log=show_log)
        if not sent_result:
            return False

        # 存储消息到数据库
        try:
            if storage_message:
                with get_db_session() as db_session:
                    MessageUtils.fill_reply_frequency_if_available(message)
                    db_session.add(message.to_db_instance())
        except Exception as e:
            logger.error(f"[{message.session_id}] 存储消息 {message.message_id} 时出错：{e}")
            raise e

        return True

    @staticmethod
    async def _broadcast_message_to_plugins(message: "SessionMessage"):
        """广播消息到所有注册的插件"""
        # TODO: 实现消息广播逻辑
        raise NotImplementedError("消息广播到插件的功能尚未实现")

    @staticmethod
    async def _send_message_via_maim_message(message: "SessionMessage", show_log: bool = True) -> bool:
        """
        通过 MAIM Message API 发送消息

        参数：
            message: SessionMessage 对象
            show_log: 是否显示日志

        返回：
            bool: 消息是否发送成功
        """
        # TODO: 重构至新的发送模型
        message_preview = (message.processed_plain_text or "")[:200]

        try:
            # 尝试通过主 API 发送
            try:
                message_base = await message.to_maim_message()
                send_result = await get_global_api().send_message(message_base)
                if not send_result:
                    # Legacy API 返回 False，尝试 Fallback
                    # return await self._send_with_fallback(message, message_preview, platform, show_log)
                    return False
                if show_log:
                    logger.info(f"已将消息 '{message_preview}' 发往平台'{message.platform}'")
                return True

            except Exception:
                # # Legacy API 抛出异常，尝试 Fallback
                # return await self._send_with_fallback(
                #     message, message_preview, platform, show_log, legacy_exception=legacy_e
                # )
                return False

        except Exception as e:
            logger.error(f"发送消息 '{message_preview}' 发往平台'{message.platform}' 失败：{str(e)}")
            import traceback

            traceback.print_exc()
            raise e

    async def _send_with_fallback(
        self,
        message: "SessionMessage",
        message_preview: str,
        platform: str,
        show_log: bool,
        legacy_exception: Optional[Exception] = None,
    ) -> bool:
        """
        Fallback 发送逻辑：通过 API Server 发送

        参数：
            message: SessionMessage 对象
            message_preview: 消息预览
            platform: 目标平台
            show_log: 是否显示日志
            legacy_exception: 遗留异常（如果 Fallback 失败则抛出）

        返回：
            bool: 消息是否发送成功
        """
        try:
            from src.config.config import global_config

            # 如果未开启 API Server，直接跳过 Fallback
            if not global_config.maim_message.enable_api_server:
                logger.debug("[API Server Fallback] API Server 未开启，跳过 fallback")
                if legacy_exception:
                    raise legacy_exception
                return False

            global_api = get_global_api()
            extra_server = getattr(global_api, "extra_server", None)

            if not extra_server:
                logger.warning("[API Server Fallback] extra_server 不存在")
                if legacy_exception:
                    raise legacy_exception
                return False

            if not extra_server.is_running():
                logger.warning("[API Server Fallback] extra_server 未运行")
                if legacy_exception:
                    raise legacy_exception
                return False

            # Fallback: 使用 Platform -> API Key 映射
            platform_map = getattr(global_api, "platform_map", {})
            logger.debug(f"[API Server Fallback] platform_map: {platform_map}, 目标平台：'{platform}'")
            target_api_key = platform_map.get(platform)

            if not target_api_key:
                logger.warning(f"[API Server Fallback] 未找到平台'{platform}'的 API Key 映射")
                if legacy_exception:
                    raise legacy_exception
                return False

            # 使用 MessageConverter 转换为 API 消息
            from maim_message import MessageConverter

            # 新架构：通过 to_maim_message() 转换，内部已处理私聊/群聊的 user_info 差异
            message_base = await message.to_maim_message()

            api_message = MessageConverter.to_api_send(
                message=message_base,
                api_key=target_api_key,
                platform=platform,
            )

            # 直接调用 Server 的 send_message 接口，它会自动处理路由
            logger.debug("[API Server Fallback] 正在通过 extra_server 发送消息...")
            results = await extra_server.send_message(api_message)
            logger.debug(f"[API Server Fallback] 发送结果：{results}")

            # 检查是否有任何连接发送成功
            if any(results.values()):
                if show_log:
                    logger.info(
                        f"已通过 API Server Fallback 将消息 '{message_preview}' 发往平台'{platform}' (key: {target_api_key})"
                    )
                return True
            else:
                logger.warning(f"[API Server Fallback] 没有连接发送成功，results={results}")

        except Exception as e:
            logger.error(f"[API Server Fallback] 发生异常：{e}")
            import traceback

            logger.debug(traceback.format_exc())

        # 如果 Fallback 失败，且存在 legacy 异常，则抛出 legacy 异常
        if legacy_exception:
            raise legacy_exception
        return False
