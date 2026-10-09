"""用真实 SDK 核对各能力返回值的归一化契约（transport 模拟，SDK 为真）。"""

from __future__ import annotations

from helpers import MAIN_QQ, MockTransport, build_stream, make_plugin, run


def test_chat_get_stream_by_user_id_returns_stream_body(tmp_path):
    transport = MockTransport()
    _plugin, ctx = make_plugin(transport, tmp_path)
    stream = run(ctx.chat.get_stream_by_user_id(user_id=MAIN_QQ, platform="qq"))
    assert isinstance(stream, dict)
    assert stream.get("stream_id")
    # 不是 {success, stream} 包装
    assert "success" not in stream or "stream" not in stream
    assert stream.get("chat_type") == "private"


def test_message_get_by_time_in_chat_returns_list(tmp_path):
    transport = MockTransport()
    _plugin, ctx = make_plugin(transport, tmp_path)
    messages = run(ctx.message.get_by_time_in_chat(chat_id="s", start_time="0", end_time="9999999999"))
    assert isinstance(messages, list)


def test_message_get_recent_returns_list(tmp_path):
    transport = MockTransport()
    _plugin, ctx = make_plugin(transport, tmp_path)
    messages = run(ctx.message.get_recent(chat_id="s", limit=5))
    assert isinstance(messages, list)


def test_llm_generate_returns_response_payload(tmp_path):
    transport = MockTransport()
    _plugin, ctx = make_plugin(transport, tmp_path)
    result = run(ctx.llm.generate(prompt="hi", task_name="utils"))
    assert isinstance(result, dict)
    assert result.get("success") is True
    assert isinstance(result.get("response"), str)
    assert result.get("model") == "gpt-5.6-sol"


def test_proactive_trigger_reports_queued_not_sent(tmp_path):
    transport = MockTransport()
    _plugin, ctx = make_plugin(transport, tmp_path)
    result = run(ctx.maisaka.proactive.trigger(stream_id="s", intent="hi"))
    assert isinstance(result, dict)
    assert result.get("success") is True
    assert result.get("queued") is True
    assert "sent" not in result


def test_api_call_returns_target_api_result(tmp_path):
    transport = MockTransport()
    transport.api_result = {"success": True, "result": {"result": True, "message": "ok", "data": [{"content": "x"}]}}
    _plugin, ctx = make_plugin(transport, tmp_path)
    result = run(ctx.api.call("internetsb.maizone.get_feeds_list_api", target_qq=MAIN_QQ, num=3, filter=False))
    assert isinstance(result, dict)
    assert result.get("result") is True
    assert result.get("data") == [{"content": "x"}]


def test_group_stream_is_marked_group(tmp_path):
    transport = MockTransport()
    transport.stream = build_stream(group=True)
    _plugin, ctx = make_plugin(transport, tmp_path)
    stream = run(ctx.chat.get_stream_by_user_id(user_id=MAIN_QQ, platform="qq"))
    assert stream.get("chat_type") == "group"
    assert stream.get("is_group_session") is True
    assert stream.get("group_id")
