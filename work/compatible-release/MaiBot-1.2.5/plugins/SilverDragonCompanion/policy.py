"""银白龙主动聊天时间与频率策略（纯函数，便于离线测试）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    """返回带北京时区（+08:00）的当前时间。"""
    return datetime.now(BEIJING_TZ)


def utc_now() -> datetime:
    """返回带时区的当前时间（用于 TTL / 持久化比较）。"""
    return datetime.now(timezone.utc)


def to_beijing(value: datetime) -> datetime:
    """把任意 aware datetime 归一化到北京时区。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def beijing_date(value: datetime) -> str:
    """返回北京时区日期字符串 YYYY-MM-DD。"""
    return to_beijing(value).strftime("%Y-%m-%d")


def in_silent_hours(now: datetime, start_hour: int, end_hour: int) -> bool:
    """判断当前北京时间是否落在静默时段 [start_hour, end_hour)。

    支持跨零点（如 22:00～06:00）。start_hour == end_hour 视为不静默。
    """
    hour = to_beijing(now).hour
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def parse_iso(value: str | None) -> datetime | None:
    """解析带时区 ISO 字符串；无时区时按北京时区解释。"""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING_TZ)
    return parsed


def clamp_minutes(value: Any, minimum: int, maximum: int) -> int:
    """把模型给出的分钟数钳制到 [minimum, maximum] 整数；非法值退避到 minimum。"""
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    try:
        minutes = int(round(float(value)))
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(maximum, minutes))


def minutes_from_now_to_iso(now: datetime, minutes: int) -> str:
    """返回 now + minutes 分钟的 ISO 字符串。"""
    return (to_beijing(now) + timedelta(minutes=minutes)).isoformat()


def seconds_between(now: datetime, earlier: str | None) -> float | None:
    """返回 now 与 earlier（ISO）之间的秒数；earlier 缺失/非法时返回 None。"""
    parsed = parse_iso(earlier)
    if parsed is None:
        return None
    return (now - parsed).total_seconds()


def within_min_interval(now: datetime, last_trigger_at: str | None, interval_minutes: int) -> bool:
    """判断距上次触发是否还不满最小间隔。"""
    elapsed = seconds_between(now, last_trigger_at)
    if elapsed is None:
        return False
    return elapsed < interval_minutes * 60


def next_after_silence(now: datetime, start_hour: int, end_hour: int) -> datetime:
    """返回静默时段结束后第一个严格晚于 now 的时刻（北京时间）。"""
    bj = to_beijing(now)
    if start_hour == end_hour:
        return bj + timedelta(minutes=15)
    candidate = bj.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if candidate <= bj:
        candidate += timedelta(days=1)
    return candidate


def next_day_after_silence(now: datetime, start_hour: int, end_hour: int) -> datetime:
    """返回明天静默时段结束时刻（北京时间），用于每日触发上限后的复位。"""
    del start_hour
    nxt = to_beijing(now) + timedelta(days=1)
    return nxt.replace(hour=end_hour, minute=0, second=0, microsecond=0)
