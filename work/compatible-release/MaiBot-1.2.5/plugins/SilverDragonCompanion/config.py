"""银白龙主动聊天插件配置模型。"""

from __future__ import annotations

from maibot_sdk import Field, PluginConfigBase


class PluginSectionConfig(PluginConfigBase):
    """插件开关。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=False, description="是否启用主动聊天调度")
    config_version: str = Field(default="1.0.0", description="配置版本")


class TargetConfig(PluginConfigBase):
    """主动聊天目标：仅允许配置中的真实主号 QQ 私聊。"""

    __ui_label__ = "主号"
    __ui_icon__ = "user"
    __ui_order__ = 1

    main_qq: str = Field(default="", description="真实主号 QQ（仅私聊该账号）；留空默认拒绝一切主动触发")
    bot_qq: str = Field(default="", description="机器人小号 QQ，用于区分消息角色；留空时非主号消息判为机器人")


class PolicyConfig(PluginConfigBase):
    """调度策略与频率上限（这些只是安全上限，不是固定聊天时刻）。"""

    __ui_label__ = "调度策略"
    __ui_icon__ = "calendar-clock"
    __ui_order__ = 2

    next_check_min_minutes: int = Field(default=15, ge=15, le=360, description="下次评估最短间隔（分钟）")
    next_check_max_minutes: int = Field(default=360, ge=15, le=1440, description="下次评估最长间隔（分钟）")
    min_trigger_interval_minutes: int = Field(default=60, ge=1, le=1440, description="两次主动触发最小间隔（分钟）")
    max_triggers_per_day: int = Field(default=3, ge=1, le=24, description="每天最多主动触发次数")
    silent_start_hour: int = Field(default=0, ge=0, le=23, description="静默开始小时（北京时间，左闭右开）")
    silent_end_hour: int = Field(default=8, ge=0, le=23, description="静默结束小时（北京时间，左闭右开）")
    startup_recent_chat_silence_minutes: int = Field(
        default=5, ge=0, le=120, description="启动时最近 N 分钟有聊天则先静默"
    )
    ongoing_chat_seconds: int = Field(
        default=120, ge=0, le=3600, description="入队前判定聊天进行中的时间窗（秒）"
    )
    history_days: int = Field(default=7, ge=1, le=30, description="采集主号私聊历史的天数")
    history_max_messages: int = Field(default=40, ge=1, le=200, description="采集主号私聊历史的最大条数")
    feeds_count: int = Field(default=3, ge=0, le=10, description="读取主号空间动态条数（0 关闭）")
    model_task_name: str = Field(default="utils", description="调度决策复用现有宿主模型任务 utils，不更换模型")


class NewsConfig(PluginConfigBase):
    """新闻参考（可选话题，仅取标题/链接/日期，不作为指令执行）。"""

    __ui_label__ = "新闻"
    __ui_icon__ = "newspaper"
    __ui_order__ = 3

    enabled: bool = Field(default=True, description="是否读取当天新闻作为可选话题")
    urls: list[str] = Field(
        default_factory=lambda: [
            "https://www.ithome.com/rss/",
            "https://www.chinanews.com.cn/rss/scroll-news.xml",
        ],
        description="RSS 源列表",
    )
    fetch_timeout_seconds: int = Field(default=8, ge=1, le=60, description="单源抓取超时（秒）")
    cache_seconds: int = Field(default=300, ge=10, le=3600, description="新闻结果缓存（秒）")
    max_bytes: int = Field(default=200000, ge=1000, le=5000000, description="单源响应体大小上限（字节）")


class CompanionConfig(PluginConfigBase):
    """银白龙主动聊天插件总配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    news: NewsConfig = Field(default_factory=NewsConfig)
