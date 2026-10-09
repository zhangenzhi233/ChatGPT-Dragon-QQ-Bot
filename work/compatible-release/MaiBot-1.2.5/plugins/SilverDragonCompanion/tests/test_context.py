"""上下文采集：私聊核验、角色/时间统计、空间解析。"""

from __future__ import annotations

from helpers import BOT_QQ, MAIN_QQ, MockTransport, build_message, build_stream, make_plugin, run


def test_resolve_private_stream_ok(tmp_path):
    transport = MockTransport()
    plugin, _ctx = make_plugin(transport, tmp_path)
    from SilverDragonCompanion.context import ContextGatherer

    gatherer = ContextGatherer(plugin)
    stream = run(gatherer.resolve_private_stream(MAIN_QQ))
    assert stream is not None
    assert stream["chat_type"] == "private"


def test_resolve_group_stream_rejected(tmp_path):
    transport = MockTransport()
    transport.stream = build_stream(group=True)
    plugin, _ctx = make_plugin(transport, tmp_path)
    from SilverDragonCompanion.context import ContextGatherer

    gatherer = ContextGatherer(plugin)
    stream = run(gatherer.resolve_private_stream(MAIN_QQ))
    assert stream is None


def test_resolve_mismatched_user_rejected(tmp_path):
    transport = MockTransport()
    transport.stream = build_stream()
    transport.stream["user_id"] = "someone-else"
    plugin, _ctx = make_plugin(transport, tmp_path)
    from SilverDragonCompanion.context import ContextGatherer

    gatherer = ContextGatherer(plugin)
    stream = run(gatherer.resolve_private_stream(MAIN_QQ))
    assert stream is None


def test_gather_chat_roles_and_stats(tmp_path):
    transport = MockTransport()
    import time

    now = time.time()
    transport.messages = [
        build_message(text="bot 早", from_user=False, ts=now - 3600, message_id="b1"),
        build_message(text="你好", from_user=True, ts=now - 60, message_id="u1"),
    ]
    plugin, _ctx = make_plugin(transport, tmp_path)
    from SilverDragonCompanion.context import ContextGatherer

    gatherer = ContextGatherer(plugin)
    snap = run(gatherer.gather_chat(stream_id="sess-main", main_qq=MAIN_QQ, bot_qq=BOT_QQ, days=7, max_messages=40))
    assert snap.available is True
    assert len(snap.messages) == 2
    assert snap.last_user_at is not None
    assert snap.last_bot_at is not None
    # 最后一条是主号，且仍在等待回复
    assert snap.user_waits_seconds is not None
    assert snap.user_waits_seconds <= 70


def test_gather_chat_skips_notify_and_group(tmp_path):
    transport = MockTransport()
    import time

    now = time.time()
    group_msg = build_message(text="群消息", from_user=True, ts=now - 10, message_id="g1")
    group_msg["message_info"]["group_info"] = {"group_id": "111", "group_name": "群"}
    notify_msg = build_message(text="通知", from_user=False, ts=now - 5, message_id="n1")
    notify_msg["is_notify"] = True
    transport.messages = [group_msg, notify_msg]
    plugin, _ctx = make_plugin(transport, tmp_path)
    from SilverDragonCompanion.context import ContextGatherer

    gatherer = ContextGatherer(plugin)
    snap = run(gatherer.gather_chat(stream_id="sess-main", main_qq=MAIN_QQ, bot_qq=BOT_QQ, days=7, max_messages=40))
    assert snap.available is True  # 查询成功、可读消息为空，与查询失败不同。
    assert snap.messages == []


def test_gather_feeds_returns_data(tmp_path):
    transport = MockTransport()
    transport.api_result = {
        "success": True,
        "result": {"result": True, "message": "ok", "data": [{"content": "今天天气不错", "created_time": "2026-10-08 09:00"}]},
    }
    plugin, _ctx = make_plugin(transport, tmp_path)
    from SilverDragonCompanion.context import ContextGatherer

    gatherer = ContextGatherer(plugin)
    feeds = run(gatherer.gather_feeds(main_qq=MAIN_QQ, bot_qq=BOT_QQ, count=3))
    assert feeds is not None
    assert feeds[0]["content"] == "今天天气不错"


def test_gather_feeds_unavailable_on_failure(tmp_path):
    transport = MockTransport()
    transport.api_result = {"success": True, "result": {"result": False, "message": "fail", "data": []}}
    plugin, _ctx = make_plugin(transport, tmp_path)
    from SilverDragonCompanion.context import ContextGatherer

    gatherer = ContextGatherer(plugin)
    feeds = run(gatherer.gather_feeds(main_qq=MAIN_QQ, bot_qq=BOT_QQ, count=3))
    assert feeds is None
