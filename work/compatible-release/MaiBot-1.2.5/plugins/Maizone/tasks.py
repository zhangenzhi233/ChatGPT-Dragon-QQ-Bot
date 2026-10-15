import datetime
import asyncio
import random
import time
import json
from pathlib import Path
from .utils import read_feed, monitor_read_feed, reply_feed, prepare_feed, publish_prepared_feed

# ===== logger =====
class NoLogger:
    def info(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass
    def debug(self, msg):
        pass
logger = NoLogger()
def set_tasks_logger(custom_logger):
    global logger
    logger = custom_logger


def _is_in_silent_period(silent_hours_config: str) -> bool:
    """
    检查当前时间是否在静默时间段内

    Args:
        silent_hours_config: 静默时间段配置，格式如"23:00-07:00,12:00-14:00"

    Returns:
        bool: 是否在静默时间段
    """
    if not silent_hours_config or not silent_hours_config.strip():
        return False

    try:
        now = datetime.datetime.now()
        current_time = now.hour * 60 + now.minute  # 当前时间转换为分钟数

        # 解析静默时间段
        periods = silent_hours_config.split(',')
        is_silent = False

        for period in periods:
            period = period.strip()
            if not period:
                continue

            # 解析时间段
            if '-' not in period:
                continue

            start_str, end_str = period.split('-', 1)
            start_time = _parse_time_to_minutes(start_str.strip())
            end_time = _parse_time_to_minutes(end_str.strip())

            if start_time is None or end_time is None:
                continue

            # 检查时间范围（处理跨天的情况）
            if start_time <= end_time:
                # 不跨天，如 12:00-14:00
                if start_time <= current_time <= end_time:
                    is_silent = True
                    break
            else:
                # 跨天，如 23:00-07:00
                if current_time >= start_time or current_time <= end_time:
                    is_silent = True
                    break

        # 返回是否在静默时间段
        return is_silent

    except Exception as e:
        logger.error(f"解析静默时间段配置失败: {str(e)}")
        return False


def _parse_time_to_minutes(time_str: str) -> int | None:
    """
    将时间字符串转换为分钟数

    Args:
        time_str: 时间字符串，格式"HH:MM"

    Returns:
        int: 分钟数，解析失败返回None
    """
    try:
        if ':' not in time_str:
            return None

        hour_str, minute_str = time_str.split(':', 1)
        hour = int(hour_str.strip())
        minute = int(minute_str.strip())

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour * 60 + minute
        else:
            return None

    except (ValueError, AttributeError):
        return None

# 自动发送准备阶段重排：只在 18:00~22:00 窗口内，最多重试 2 次、每次间隔 15 分钟。
PREP_RETRY_WINDOW_START = "18:00"
PREP_RETRY_WINDOW_END = "22:00"
PREP_RETRY_DELAY_MINUTES = 15
MAX_PREP_RETRIES = 2

class FeedMonitor:
    """
    说说监控任务，根据配置：阅读空间好友最新说说、阅读优先列表说说、回复自己说说下的评论
    """

    def __init__(self, plugin):
        self.plugin = plugin
        self.config = plugin.config
        self.is_running = False
        self.task = None
        self.last_check_time = 0

    async def start(self):
        """启动监控任务"""
        if self.is_running:
            return
        self.is_running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("说说监控任务已启动")

    async def stop(self):
        """停止监控任务"""
        if not self.is_running:
            return
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("说说监控任务已停止")
    
    async def _monitor_loop(self):
        """监控循环"""
        # 获取配置
        interval = self.config.auto_read.interval
        silent_duration = self.config.auto_read.silent_duration
        authority_type = self.config.authority.auto_read_authority_type
        white_list = self.config.authority.auto_read_whitelist
        while self.is_running:
            try:
                # 等待指定时间
                await asyncio.sleep(interval * 60)
                # 检查是否在静默时间段内
                if _is_in_silent_period(silent_duration):
                    continue
                # 对白名单中的QQ单独优先处理
                for qq in white_list:
                    logger.info(f"开始处理白名单中的QQ: {qq}")
                    success, message = await read_feed(qq)
                    if not success:
                        logger.warning(f"未进行任何处理: {message}")
                    else:
                        logger.info(f"已阅读{qq}的说说，数量：{len(message)}条")
                # 若是白名单模式，则跳过其他QQ
                if authority_type != "whitelist":
                    await monitor_read_feed()
                # 自动回复
                if self.config.auto_reply.enable_auto_reply:
                    await reply_feed()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控任务出错: {str(e)}")
                # 出错后等待一段时间再重试
                await asyncio.sleep(300)


class ScheduleSender:
    """
    定时发送任务，根据配置：定时发送说说
    """
    def __init__(self, plugin):
        self.plugin = plugin
        self.is_running = False
        self.task = None
        self.last_send_time = 0
        self.fluctuate_table = []  # 记录波动后的发送时间表
        self.last_reset_date = None  # 记录上次重置发送时间表日期
        self.today_send_enabled = True  # 记录今天是否允许发送说说
        self.attempted_today = False
        self.prep_retries = 0  # 当天准备阶段重试次数
        self.prep_next_at = None  # 下一次准备重试时间 "HH:MM"，None 表示无待重试
        self.state_path = Path(__file__).parent / "schedule_state.json"

    async def start(self):
        """启动定时发送任务"""
        if self.is_running:
            return
        self.is_running = True
        self.last_reset_date = datetime.datetime.now().date()
        self._generate_fluctuate_table()  # 生成时间表
        self._check_today_send_decision()  # 初始化今天的发送决策
        self._restore_today_state()
        self.task = asyncio.create_task(self._schedule_loop())
        logger.info("定时发送说说任务已启动")

    async def stop(self):
        """停止定时发送任务"""
        if not self.is_running:
            return
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("定时发送说说任务已停止")

    def _check_today_send_decision(self):
        """每天0点决定今天是否发送说说"""
        p = self.plugin.config.auto_send.daily_probability

        # 生成0-1之间的随机数，如果小于p则发送，否则不发送
        if random.random() < p:
            self.today_send_enabled = True
            logger.info(f"今天允许发送说说 (概率: {p:.2f})")
        else:
            self.today_send_enabled = False
            logger.info(f"今天不发送说说 (概率: {p:.2f})")

    def _generate_fluctuate_table(self):
        """生成随机波动时间表"""
        schedule_times = self.plugin.config.auto_send.schedule
        fluctuate_minutes = self.plugin.config.auto_send.fluctuation

        # 清空当前波动表
        self.fluctuate_table = []

        # 如果波动分钟数为0，直接使用计划时间
        if fluctuate_minutes == 0:
            self.fluctuate_table = schedule_times.copy()
            self.fluctuate_table.sort()
            logger.info(f"无波动，使用计划时间: {self.fluctuate_table}")
            return

        # 为每个计划时间生成一个随机波动时间
        for base_time in schedule_times:
            # 解析基础时间
            base_hour, base_minute = map(int, base_time.split(":"))
            base_total_minutes = base_hour * 60 + base_minute
            # 生成随机偏移量
            offset = random.randint(-fluctuate_minutes, fluctuate_minutes)
            # 处理溢出
            total_minutes = base_total_minutes + offset
            if total_minutes < 0:
                total_minutes += 24 * 60
            elif total_minutes >= 24 * 60:
                total_minutes -= 24 * 60
            # 转换回时间格式
            h = total_minutes // 60
            m = total_minutes % 60
            fluctuate_time = f"{h:02d}:{m:02d}"
            # 添加到波动表
            if fluctuate_time not in self.fluctuate_table:
                self.fluctuate_table.append(fluctuate_time)

        # 按时间排序波动表
        self.fluctuate_table.sort()
        logger.info(f"波动后的发送时间表: {self.fluctuate_table}")

    def _should_reset_schedule(self):
        """检查是否需要重置时间表（每天0点）"""
        current_date = datetime.datetime.now().date()
        return current_date != self.last_reset_date

    def _save_state(self) -> bool:
        """随机计划与发布/准备记账原子保存，进程重启后沿用；返回是否写入成功。"""
        value = {
            "date": self.last_reset_date.isoformat(),
            "times": self.fluctuate_table,
            "send_enabled": self.today_send_enabled,
            "attempted": self.attempted_today,
            "prep_retries": self.prep_retries,
            "prep_next_at": self.prep_next_at or "",
        }
        try:
            temporary = self.state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.state_path)
            return True
        except Exception as exc:
            logger.error(f"写入计划状态失败，拒绝自动发布: {exc}")
            self.today_send_enabled = False
            self.attempted_today = True
            self.fluctuate_table = []
            self.prep_next_at = None
            return False

    def _restore_today_state(self):
        """恢复当天状态；状态文件损坏时拒绝发布（视为已消费，不补发）。"""
        if self.state_path.exists():
            try:
                value = json.loads(self.state_path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("计划状态必须为对象")
                datetime.date.fromisoformat(value["date"])
                if type(value.get("attempted")) is not bool or type(value.get("send_enabled")) is not bool:
                    raise ValueError("计划开关类型错误")
                times = value.get("times")
                if not isinstance(times, list) or any(not isinstance(t, str) or _parse_time_to_minutes(t) is None for t in times):
                    raise ValueError("计划时间无效")
                retries = value.get("prep_retries", 0)
                if type(retries) is not int or not 0 <= retries <= MAX_PREP_RETRIES:
                    raise ValueError("准备重试次数无效")
                next_at = value.get("prep_next_at", "")
                if not isinstance(next_at, str) or (next_at and _parse_time_to_minutes(next_at) is None):
                    raise ValueError("准备重试时间无效")
            except Exception as exc:
                logger.error(f"计划状态文件损坏，拒绝自动发布: {exc}")
                self.today_send_enabled = False
                self.attempted_today = True
                self.fluctuate_table = []
                self.prep_retries = 0
                self.prep_next_at = None
                return
            if isinstance(value, dict) and value.get("date") == self.last_reset_date.isoformat():
                self.today_send_enabled = bool(value.get("send_enabled", False))
                self.attempted_today = bool(value.get("attempted", False))
                self.fluctuate_table = [] if self.attempted_today else list(value.get("times", []))
                self.prep_retries = int(value.get("prep_retries", 0) or 0)
                raw_next = value.get("prep_next_at", "")
                self.prep_next_at = str(raw_next) if raw_next else None
        self._save_state()

    def mark_attempted_today(self) -> bool:
        """在即将首次调用 publish_emotion 前持久记账；失败/回执不明当天不重发。

        返回是否记账成功；写状态失败时调用方必须拒绝发布。
        """
        self.attempted_today = True
        self.fluctuate_table = []
        self.prep_next_at = None
        return self._save_state()

    async def _schedule_loop(self):
        """定时发送循环"""
        while self.is_running:
            try:
                # 检查是否需要重置时间表（每天0点）
                if self._should_reset_schedule():
                    logger.info("检测到日期变化，重置发送时间表")
                    self.last_reset_date = datetime.datetime.now().date()
                    self.attempted_today = False
                    self.prep_retries = 0
                    self.prep_next_at = None
                    self._generate_fluctuate_table()
                    self._check_today_send_decision()  # 重新决定今天是否发送
                    self._save_state()

                # 获取当前时间
                current_time = datetime.datetime.now().strftime("%H:%M")

                # 1) 待重试的准备（prep_next_at）已到时间，优先执行准备重试。
                if (
                    self.today_send_enabled
                    and not self.attempted_today
                    and self.prep_next_at is not None
                    and current_time >= self.prep_next_at
                ):
                    self.prep_next_at = None  # 消费本次重试
                    if not self._save_state():
                        continue
                    if not self._is_within_prep_retry_window(datetime.datetime.now()):
                        logger.info("错过准备重试窗口，取消本次重试")
                        continue
                    await self._attempt_prepare_and_publish()
                elif current_time in self.fluctuate_table and self.today_send_enabled:
                    # 2) 到达计划时间点
                    if time.time() - self.last_send_time >= 60:  # 避免一分钟内重复发送
                        logger.info(f"当前时间 {current_time} ，准备发送说说")
                        self.last_send_time = time.time()
                        self.fluctuate_table.remove(current_time)
                        self._save_state()
                        await self._attempt_prepare_and_publish()
                        logger.info(f"剩余发送时间点: {self.fluctuate_table}")
                elif current_time in self.fluctuate_table and not self.today_send_enabled:
                    # 如果到达发送时间但今天不允许发送，也移除该时间点
                    logger.info(f"到达发送时间 {current_time}，但今天不发送说说")
                    self.fluctuate_table.remove(current_time)
                    self._save_state()
                    logger.info(f"剩余发送时间点: {self.fluctuate_table}")

                await asyncio.sleep(60)  # 每分钟检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"定时发送任务出错: {e}")
                await asyncio.sleep(60)

    async def _attempt_prepare_and_publish(self):
        """准备正文与配图；仅在准备成功且能记账时才发布。"""
        if self.attempted_today or not self.today_send_enabled:
            return
        enable_random_topic = self.plugin.config.auto_send.random_topic
        fixed_topic = self.plugin.config.auto_send.fixed_topic
        try:
            topic = "随机主题" if enable_random_topic else random.choice(fixed_topic)
            ok, prepared_or_error = await prepare_feed(topic)
        except Exception as exc:
            logger.error(f"准备说说异常，尚未发布: {exc}")
            self._schedule_prep_retry()
            return
        if not ok:
            logger.error(f"准备说说失败: {prepared_or_error}")
            self._schedule_prep_retry()
            return

        # 即将首次调用 publish_emotion：此刻持久记账；写失败则拒绝发布。
        if not self.mark_attempted_today():
            logger.error("准备完成但无法记账，拒绝发布")
            return

        success, message = await publish_prepared_feed(prepared_or_error)
        if success:
            logger.info(f"已成功发送定时说说: {topic}")
        else:
            logger.error(f"发布定时说说失败（当天不再重试）: {message}")

    def _schedule_prep_retry(self) -> None:
        """准备阶段失败时，在 18:00~22:00 窗口内安排有限重试（最多 2 次）。"""
        if self.attempted_today:
            return
        now = datetime.datetime.now()
        if not self._is_within_prep_retry_window(now):
            logger.info("准备失败但已不在 18:00~22:00 窗口内，不安排重试")
            self.prep_next_at = None
            self._save_state()
            return
        if self.prep_retries >= MAX_PREP_RETRIES:
            logger.info(f"准备重试已达上限（{MAX_PREP_RETRIES} 次），当天不再自动发布")
            self.prep_next_at = None
            self._save_state()
            return
        next_at = now + datetime.timedelta(minutes=PREP_RETRY_DELAY_MINUTES)
        window_end = _parse_time_to_minutes(PREP_RETRY_WINDOW_END)
        if window_end is not None:
            window_end_dt = now.replace(hour=window_end // 60, minute=window_end % 60, second=0, microsecond=0)
            if next_at > window_end_dt:
                self.prep_next_at = None
                self._save_state()
                logger.info("15 分钟后的重试已超出窗口，不安排重试")
                return
        self.prep_retries += 1
        self.prep_next_at = next_at.strftime("%H:%M")
        self._save_state()
        logger.info(
            f"准备失败，安排 {PREP_RETRY_DELAY_MINUTES} 分钟后重试"
            f"（第 {self.prep_retries}/{MAX_PREP_RETRIES} 次）: {self.prep_next_at}"
        )

    def _is_within_prep_retry_window(self, now: datetime.datetime) -> bool:
        """判断当前时间是否在 18:00~22:00 重排窗口内。"""
        start = _parse_time_to_minutes(PREP_RETRY_WINDOW_START)
        end = _parse_time_to_minutes(PREP_RETRY_WINDOW_END)
        if start is None or end is None:
            return False
        current = now.hour * 60 + now.minute
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end
