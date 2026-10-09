"""提示词构建与结构化解析测试。"""

from __future__ import annotations

from datetime import datetime

from SilverDragonCompanion.context import ChatSnapshot
from SilverDragonCompanion.news import NewsReport
from SilverDragonCompanion.policy import BEIJING_TZ
from SilverDragonCompanion.prompts import build_prompt, parse_decision


def test_parse_silence_with_variable_next_time():
    decision = parse_decision('{"should_chat": false, "next_check_minutes": 200, "reason": "r"}', min_minutes=15, max_minutes=360)
    assert decision.should_chat is False
    assert decision.next_check_minutes == 200


def test_parse_chat_with_topic():
    decision = parse_decision(
        '{"should_chat": true, "topic": "天气", "intent": "聊天气", "next_check_minutes": 60, "reason": "r"}',
        min_minutes=15,
        max_minutes=360,
    )
    assert decision.should_chat is True
    assert decision.topic == "天气"
    assert decision.intent == "聊天气"


def test_parse_clamps_out_of_range():
    decision = parse_decision('{"should_chat": false, "next_check_minutes": 5}', min_minutes=15, max_minutes=360)
    assert decision.next_check_minutes == 15
    decision = parse_decision('{"should_chat": false, "next_check_minutes": 999}', min_minutes=15, max_minutes=360)
    assert decision.next_check_minutes == 360


def test_parse_failure_silent_with_min_fallback():
    decision = parse_decision("今天没有话题", min_minutes=15, max_minutes=360)
    assert decision.should_chat is False
    assert decision.parse_error
    assert decision.next_check_minutes == 15


def test_parse_strips_code_fence():
    decision = parse_decision('```json\n{"should_chat": false, "next_check_minutes": 30}\n```', min_minutes=15, max_minutes=360)
    assert decision.should_chat is False
    assert decision.next_check_minutes == 30


def test_build_prompt_contains_blocks():
    chat = ChatSnapshot(available=True, messages=[{"role": "user", "time": "2026-10-08T09:00:00+08:00", "text": "你好"}])
    prompt = build_prompt(
        now=datetime(2026, 10, 8, 10, 0, tzinfo=BEIJING_TZ),
        chat=chat,
        feeds=None,
        news=NewsReport(),
        min_minutes=15,
        max_minutes=360,
    )
    assert "你好" in prompt
    assert "主号空间动态" in prompt
    assert "当天新闻" in prompt
    assert "15" in prompt and "360" in prompt
