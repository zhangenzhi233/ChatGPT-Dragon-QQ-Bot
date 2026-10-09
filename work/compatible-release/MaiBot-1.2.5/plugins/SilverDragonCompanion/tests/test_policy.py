"""时间与频率策略纯函数测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from SilverDragonCompanion.policy import (
    BEIJING_TZ,
    beijing_date,
    clamp_minutes,
    in_silent_hours,
    minutes_from_now_to_iso,
    next_after_silence,
    next_day_after_silence,
    parse_iso,
    within_min_interval,
)


def _bj(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 8, hour, minute, tzinfo=BEIJING_TZ)


def test_silent_hours_within_window():
    assert in_silent_hours(_bj(0), 0, 8) is True
    assert in_silent_hours(_bj(7, 59), 0, 8) is True
    assert in_silent_hours(_bj(8), 0, 8) is False
    assert in_silent_hours(_bj(12), 0, 8) is False


def test_silent_hours_across_midnight():
    assert in_silent_hours(_bj(23), 22, 6) is True
    assert in_silent_hours(_bj(2), 22, 6) is True
    assert in_silent_hours(_bj(7), 22, 6) is False


def test_clamp_minutes_bounds_and_fallback():
    assert clamp_minutes(5, 15, 360) == 15
    assert clamp_minutes(500, 15, 360) == 360
    assert clamp_minutes(120, 15, 360) == 120
    assert clamp_minutes(None, 15, 360) == 15
    assert clamp_minutes("abc", 15, 360) == 15


def test_beijing_date_and_parse():
    assert beijing_date(_bj(9)) == "2026-10-08"
    assert parse_iso("2026-10-08T09:00:00+08:00").hour == 9
    assert parse_iso("not-a-date") is None
    assert parse_iso(None) is None


def test_next_after_silence_future():
    # 静默期内（00:00～08:00）下一个非静默点是当天 08:00
    assert next_after_silence(_bj(3), 0, 8).hour == 8
    assert next_after_silence(_bj(3), 0, 8).day == 8
    # 已过静默结束点 → 明天 08:00
    assert next_after_silence(_bj(9), 0, 8).day == 9
    assert next_after_silence(_bj(9), 0, 8).hour == 8


def test_next_day_after_silence():
    nxt = next_day_after_silence(_bj(12), 0, 8)
    assert nxt.day == 9
    assert nxt.hour == 8


def test_within_min_interval():
    now = _bj(10)
    last = minutes_from_now_to_iso(now, -30)  # 30 分钟前
    assert within_min_interval(now, last, 60) is True
    last = minutes_from_now_to_iso(now, -90)  # 90 分钟前
    assert within_min_interval(now, last, 60) is False
    assert within_min_interval(now, None, 60) is False


def test_utc_comparison_ttl_style():
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(seconds=600)
    assert (now - earlier).total_seconds() == 600.0
