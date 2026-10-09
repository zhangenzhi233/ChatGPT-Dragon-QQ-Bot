from maibot_sdk import Command, MaiBotPlugin, Tool, API
from maibot_sdk.types import ToolParameterInfo, ToolParamType
from pathlib import Path

import asyncio
import datetime
import json

from .config import MaizonePluginConfig
from .cookie import renew_cookies, set_api_capability, set_cookie_logger
from .qzone_api import create_qzone_api, set_qzoneapi_logger
from .image import set_images_plugin_context
from .utils import set_utils_plugin_context, read_feed, send_feed
from .tasks import FeedMonitor, ScheduleSender, set_tasks_logger


class MaizonePlugin(MaiBotPlugin):
    config_model = MaizonePluginConfig
    personality = ""
    reply_style = ""

    async def on_load(self):
        """插件加载：检查配置、测试napcat连接、注册定时任务等"""
        set_api_capability(self.ctx.api)
        set_tasks_logger(self.ctx.logger)
        set_qzoneapi_logger(self.ctx.logger)
        set_cookie_logger(self.ctx.logger)
        set_utils_plugin_context(self)
        set_images_plugin_context(self)

        # ===== 检查文本模型是否可用 =====
        available_models = await self.ctx.llm.get_available_models()
        text_model = self.config.plugin.text_model  # type: ignore
        if text_model not in available_models:
            self.ctx.logger.error(f"文本模型{text_model}不可用，请检查配置")

        # ===== 测试通过adapter或napcat获取cookie =====
        napcat_host = self.config.plugin.http_host  # type: ignore
        napcat_port = self.config.plugin.http_port  # type: ignore
        napcat_token = self.config.plugin.napcat_token  # type: ignore
        if not await renew_cookies(napcat_host, napcat_port, napcat_token, ['adapter'], False) and not await renew_cookies(napcat_host, napcat_port, napcat_token, ['napcat'], False):
            self.ctx.logger.error("通过Napcat获取Cookie失败，请检查配置，或忍受手动扫码登录的麻烦")
        else:
            self.ctx.logger.info("Napcat成功连接")

        # ===== 从主程序获取人格，表达方式等配置 =====
        self.ctx.logger.info("正在加载人格配置...")
        global_config = await self.ctx.config.get("personality", "fail")
        self.personality = global_config.get("personality", "未知")
        self.reply_style = global_config.get("reply_style", "未知")
        self.ctx.logger.info(f"已加载人格配置：personality={self.personality}, reply_style={self.reply_style}")

        # ===== 定时任务注册 =====
        if self.config.auto_read.enable_auto_read:  # type: ignore
            self.feed_monitor = FeedMonitor(self)
            await self.feed_monitor.start()
        if self.config.auto_send.enable_auto_send:  # type: ignore
            self.schedule_sender = ScheduleSender(self)
            await self.schedule_sender.start()
        # 本机明确准备的一次首次发布，使用与定时任务相同的完整发送链路。
        if (Path(__file__).parent / "initial-feed-request.json").exists():
            if hasattr(self, "schedule_sender"):
                self.schedule_sender.mark_attempted_today()
            self.initial_feed_task = asyncio.create_task(self._publish_initial_feed())

    async def _publish_initial_feed(self):
        root = Path(__file__).parent
        request = root / "initial-feed-request.json"
        consumed = root / "initial-feed-consumed.json"
        if consumed.exists():
            self.ctx.logger.error("首次发布已执行过，拒绝重复触发")
            return
        request.replace(consumed)
        if hasattr(self, "schedule_sender"):
            self.schedule_sender.mark_attempted_today()
        result = {"attempted_at": datetime.datetime.now().astimezone().isoformat(), "automatic_retry": False}
        try:
            topic = json.loads(consumed.read_text(encoding="utf-8"))["topic"]
            success, message = await send_feed(topic)
            result.update(success=success, message=message)
        except Exception as exc:
            result.update(success=False, error_type=type(exc).__name__)
            self.ctx.logger.error(f"首次空间发布未成功: {type(exc).__name__}")
        (root / "initial-feed-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    async def on_unload(self):
        """插件卸载：取消定时任务、清理资源等"""
        if hasattr(self, "initial_feed_task") and not self.initial_feed_task.done():
            self.initial_feed_task.cancel()
            try:
                await self.initial_feed_task
            except asyncio.CancelledError:
                pass
        if hasattr(self, "feed_monitor"):
            await self.feed_monitor.stop()
        if hasattr(self, "schedule_sender"):
            await self.schedule_sender.stop()

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str):
        """配置热更新后同步任务启停，暂停自动发布立即生效。"""
        del scope
        del config_data
        del version
        if hasattr(self, "schedule_sender"):
            await self.schedule_sender.stop()
        if self.config.auto_send.enable_auto_send:
            self.schedule_sender = ScheduleSender(self)
            await self.schedule_sender.start()
        if hasattr(self, "feed_monitor"):
            await self.feed_monitor.stop()
        if self.config.auto_read.enable_auto_read:
            self.feed_monitor = FeedMonitor(self)
            await self.feed_monitor.start()

    # 权限检查
    def check_permission(self, qq_account: str, tool: str) -> bool:
        """检查qq_account是否有权限使用tool工具
        参数：
        qq_account: QQ账号
        tool: 可为send_feed、read_fead
        """
        qq_account = str(qq_account or "").strip()
        if not qq_account:
            return False
        send_authority_type = self.config.authority.send_authority_type  # type: ignore
        send_whitelist = self.config.authority.send_whitelist  # type: ignore
        send_blacklist = self.config.authority.send_blacklist  # type: ignore
        read_authority_type = self.config.authority.read_authority_type  # type: ignore
        read_whitelist = self.config.authority.read_whitelist  # type: ignore
        read_blacklist = self.config.authority.read_blacklist  # type: ignore
        if tool == "send_feed":
            if send_authority_type == 'whitelist':
                return qq_account in send_whitelist
            elif send_authority_type == 'blacklist':
                return qq_account not in send_blacklist
            else:
                self.ctx.logger.error('send_authority_type错误')
                return False
        elif tool == "read_feed":
            if read_authority_type == 'whitelist':
                return qq_account in read_whitelist
            elif read_authority_type == 'blacklist':
                return qq_account not in read_blacklist
            else:
                self.ctx.logger.error('read_authority_type错误')
                return False
        else:
            self.ctx.logger.error('tool参数错误')
            return False

    # ========== 发送说说 ==========
    @Command("sendfeed", pattern=r"^/sendfeed\s+(?P<topic>.+)$")
    async def handle_send_feed(self, **kwargs):
        matched = kwargs.get("matched_groups", {})
        topic = matched.get("topic", "").strip()
        stream_id = kwargs["stream_id"]
        user_id = kwargs["user_id"]
        # ===== 检查权限 =====
        if not self.check_permission(user_id, "send_feed"):
            await self.ctx.send.text("Permission denied", stream_id)
            return False, "权限不足", 1
        # ===== 发送说说 =====
        success, message = await send_feed(topic)
        if not success:
            self.ctx.logger.error(message)
        await self.ctx.send.text(message, stream_id)
        return success, message, 1

    @Tool(
        name="send_feed",
        description="用户明确想让你发动态时，根据主题立即生成说说并发布到QQ空间；可随时调用，不受每日自动发送时段限制。查询发布状态时不要调用此工具。",
        parameters=[
            ToolParameterInfo(name="topic", param_type=ToolParamType.STRING, description="说说主题", required=True),
            ToolParameterInfo(name="nickname", param_type=ToolParamType.STRING, description="可选的用户称呼，仅作显示，不参与权限验证", required=False)
        ],
    )
    async def handle_send_feed_tool(self, topic: str, nickname: str = "", **kwargs):
        # 宿主注入当前真实请求者；昵称由模型填写，不可用来授予或拒绝权限。
        del nickname
        user_id = str(kwargs.get("user_id") or "").strip()
        if kwargs.get("platform") not in (None, "", "qq"):
            return False, "当前平台无权发布 QQ 空间动态", 1
        # ===== 检查权限 =====
        if not self.check_permission(user_id, "send_feed"):
            # 由主程序回复
            return False, "该用户无权命令发送说说", 1
        # ===== 发送说说 =====
        success, message = await send_feed(topic)
        return success, message, 1

    @Tool(name="get_my_feeds", description="只读查看你自己 QQ 空间最近发过的动态和发布时间；用户问今天发了吗、想看看你的动态时调用，不会发布、点赞或评论。")
    async def handle_get_my_feeds(self, **kwargs):
        user_id = str(kwargs.get("user_id") or "").strip()
        if kwargs.get("platform") not in (None, "", "qq") or not self.check_permission(user_id, "read_feed"):
            return False, "当前请求者无权查看空间动态", 1
        await renew_cookies(self.config.plugin.http_host, self.config.plugin.http_port,
                            self.config.plugin.napcat_token, methods=self.config.plugin.cookie_methods)
        qzone = create_qzone_api()
        if qzone is None:
            return False, "空间登录不可用，无法确认最近动态", 1
        feeds = await qzone.get_list(str(qzone.uin), 5, False)
        if feeds and feeds[0].get("error"):
            return False, "空间请求未成功，无法确认最近动态", 1
        value = {"checked_at": datetime.datetime.now().astimezone().isoformat(),
                 "recent_feeds": [{"created_time": feed.get("created_time"), "content": feed.get("content"),
                                   "images_count": len(feed.get("images") or [])} for feed in feeds],
                 "automatic_schedule": "每天随机最多一条，用户要求时可以随时额外发布"}
        return True, json.dumps(value, ensure_ascii=False), 1

    # ========== 阅读空间 ==========
    @Command("readfeed",pattern=r"^/readfeed\s+(?P<target_name>.+?)(?:\s+(?P<no_reply>不回复|不评论|noreply|no-reply|nocomment))?$")
    async def handle_read_feed(self, **kwargs):
        matched = kwargs.get("matched_groups", {})
        target_name = matched.get("target_name", "").strip()
        no_reply = (matched.get("no_reply") or "").strip()
        enable_comment = not bool(no_reply)
        target_info = await self.ctx.db.get(model_name="PersonInfo", filters={"person_name": target_name}) # type: ignore
        target_qq = target_info[0].get("user_id") if target_info else ""
        stream_id = kwargs["stream_id"]
        user_id = kwargs["user_id"]
        # ===== 检查权限 =====
        self.ctx.logger.info(f"检查权限，用户ID：{user_id}")
        if not self.check_permission(user_id, "read_feed"):
            await self.ctx.send.text("Permission denied", stream_id)
            return False, "权限不足", 1
        # ===== 阅读空间 =====
        self.ctx.logger.info(
            f"开始阅读{target_name}的说说，QQ号：{target_qq}，enable_comment={enable_comment}"
        )
        success, message = await read_feed(target_qq, enable_comment=enable_comment)
        if not success:
            self.ctx.logger.error(message)
            await self.ctx.send.text(str(message), stream_id)
            return success, str(message), 1
        suffix = "（未评论）" if not enable_comment else ""
        await self.ctx.send.text(f"已阅读{len(message)}条说说{suffix}", stream_id)
        return success, str(message), 1

    @Tool(
        name="read_feed",
        description="阅读QQ空间说说；可用 enable_comment=false 只读不评论",
        parameters=[
            ToolParameterInfo(name="nickname", param_type=ToolParamType.STRING, description="要求阅读说说的用户的昵称", required=True),
            ToolParameterInfo(name="target_name", param_type=ToolParamType.STRING, description="要求阅读说说的目标用户昵称", required=True),
            ToolParameterInfo(
                name="enable_comment",
                param_type=ToolParamType.STRING,
                description="是否评论：true/false；false、否、不回复=只读不评论。默认 true",
                required=False,
            ),
        ],
    )
    async def handle_read_feed_tool(self, nickname: str, target_name: str, enable_comment: str = "true", **kwargs):
        del nickname
        user_id = str(kwargs.get("user_id") or "").strip()
        if kwargs.get("platform") not in (None, "", "qq"):
            return False, "当前平台无权读取 QQ 空间", 1
        target_info = await self.ctx.db.get(model_name="PersonInfo", filters={"person_name": target_name})
        target_qq = target_info[0].get("user_id") if target_info else ""
        # ===== 检查权限 =====
        if not self.check_permission(user_id, "read_feed"):
            # 由主程序回复
            return False, "该用户无权命令阅读说说", 1
        # ===== 阅读空间 =====
        do_comment = self._parse_enable_comment(enable_comment, default=True)
        success, message = await read_feed(target_qq, enable_comment=do_comment)
        return success, str(message), 1

    @staticmethod
    def _parse_enable_comment(value, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"", "default", "默认"}:
            return default
        if text in {"0", "false", "no", "n", "off", "否", "不", "不回复", "不评论", "skip", "none"}:
            return False
        if text in {"1", "true", "yes", "y", "on", "是", "回复", "评论"}:
            return True
        return default
    
    @API(
        name="send_feed_api",
        description="发送说说，参数：message：文本内容（可选），images：图片二进制数据列表（可选）",
        version="1",
        public=True
    )
    async def send_feed_api(self, message: str = "", images: list[bytes] = [], **kwargs):
        """API版本的发送说说工具，供其他插件调用"""
        await renew_cookies(self.config.plugin.http_host, self.config.plugin.http_port, self.config.plugin.napcat_token, ['adapter', 'napcat'], True)  # type: ignore
        qzone = create_qzone_api()
        if qzone is None:
            return {"result": False, "message": "无法创建QzoneAPI实例，发送说说失败"}
        fid = await qzone.publish_emotion(content=message, images=images)
        if fid is None:
            return {"result": False, "message": "发送说说失败"}
        else:
            return {"result": True, "message": f"说说发送成功，动态ID：{fid}"}

    @API(
        name="get_feeds_list_api",
        description="获取指定QQ号的说说列表，参数：target_qq：目标QQ号，num：获取数量（默认5），filter：是否过滤已评论过的说说（默认False）",
        version="1",
        public=True
    )
    async def get_feeds_list_api(self, target_qq: str, num: int = 5, filter: bool = False, **kwargs):
        """API版本的获取说说列表工具"""
        await renew_cookies(self.config.plugin.http_host, self.config.plugin.http_port, self.config.plugin.napcat_token, ['adapter', 'napcat'], True)  # type: ignore
        qzone = create_qzone_api()
        if qzone is None:
            return {"result": False, "message": "无法创建QzoneAPI实例，获取列表失败"}
        feeds_list = await qzone.get_list(target_qq, num, filter)
        if not feeds_list or (len(feeds_list) == 1 and "error" in feeds_list[0]):
            return {"result": False, "message": f"获取说说列表失败：{feeds_list[0].get('error', '未知错误') if feeds_list else '返回列表为空'}"}
        else:
            return {"result": True, "message": f"成功获取{len(feeds_list)}条说说", "data": feeds_list}


def create_plugin() -> MaizonePlugin:
    """创建插件实例。"""
    return MaizonePlugin()
