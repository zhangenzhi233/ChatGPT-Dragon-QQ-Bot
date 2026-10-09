from copy import deepcopy

import pytest

from plugins.Napcat_Adapter.codecs.outbound.segment_encoder import NapCatOutboundSegmentEncoder
from plugins.SilverDragonVoice.tests.test_dynamic_reply import message_payload, prepare_voice_reply
from plugins.SilverDragonVoice.tests.test_plugin import build_plugin
from src.plugin_runtime.hook_payloads import deserialize_session_message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "component",
    [
        {"type": "text", "data": "普通文字"},
        {"type": "emoji", "data": "表情说明", "hash": "emoji-hash"},
        {"type": "voice", "data": "语音正文", "hash": "voice-hash", "binary_data_base64": "YXVkaW8="},
    ],
)
async def test_qq_direct_send_removes_visible_reply_but_keeps_internal_target(component):
    plugin, _send = build_plugin()
    message = message_payload(message_id="outbound-1", text="普通文字", reply_to="inbound-1")
    message["raw_message"] = [
        {"type": "reply", "data": {"target_message_id": "inbound-1"}},
        component,
    ]
    original = deepcopy(message)
    result = await plugin.force_direct_qq_send(
        message=message,
        typing=True,
        set_reply=True,
        reply_message_id="inbound-1",
        storage_message=True,
        show_log=True,
        route_metadata={"source": "replyer"},
    )

    updated = result["modified_kwargs"]
    assert updated["set_reply"] is False
    assert updated["reply_message_id"] == "inbound-1"
    assert updated["typing"] is True
    assert updated["storage_message"] is True
    assert updated["show_log"] is True
    assert updated["route_metadata"] == {"source": "replyer"}
    assert updated["message"]["reply_to"] == "inbound-1"
    assert updated["message"]["raw_message"] == [component]
    assert original["raw_message"][0]["type"] == "reply"
    restored = deserialize_session_message(updated["message"])
    assert [item.format_name for item in restored.raw_message.components] == [component["type"]]


@pytest.mark.asyncio
async def test_non_qq_or_disabled_plugin_does_not_change_send_kwargs():
    message = message_payload(message_id="outbound-1", text="文字", reply_to="inbound-1")
    message["raw_message"] = [{"type": "reply", "data": "inbound-1"}, {"type": "text", "data": "文字"}]
    plugin, _send = build_plugin()
    telegram = {**message, "platform": "telegram"}
    assert await plugin.force_direct_qq_send(message=telegram, set_reply=True) == {"action": "continue"}

    disabled, _send = build_plugin(enabled=False)
    assert await disabled.force_direct_qq_send(message=message, set_reply=True) == {"action": "continue"}


async def _prepared_dynamic_plugin(answer: str):
    plugin, _send = build_plugin()

    async def synthesize(text):
        assert text == answer
        return b"voice-bytes"

    request = message_payload(message_id="inbound-1", text="用语音回复我")
    await prepare_voice_reply(plugin, request=request, answer=answer, reply_message_id="inbound-1")
    return plugin, synthesize


def _dynamic_outbound(answer: str) -> dict:
    message = message_payload(message_id="outbound-1", text=answer, reply_to="inbound-1")
    message["raw_message"] = [
        {"type": "reply", "data": {"target_message_id": "inbound-1"}},
        {"type": "text", "data": answer},
        {"type": "image", "data": "配图说明", "hash": "image-hash"},
        {"type": "emoji", "data": "表情说明", "hash": "emoji-hash"},
    ]
    return message


@pytest.mark.asyncio
async def test_direct_hook_before_or_after_dynamic_voice_keeps_target_and_sends_only_record(monkeypatch):
    answer = "这是本轮动态回答。"
    plugin, synthesize = await _prepared_dynamic_plugin(answer)
    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    outbound = _dynamic_outbound(answer)

    # 先转语音再清理引用：语音 nonce、内部目标和路由参数仍完整。
    converted = await plugin.convert_reply_to_voice(
        message=deepcopy(outbound), typing=True, set_reply=True, reply_message_id="inbound-1",
        storage_message=True, show_log=True, route_metadata={"source": "normal-reply"},
    )
    after_convert = await plugin.force_direct_qq_send(**converted["modified_kwargs"])
    after_message = after_convert["modified_kwargs"]["message"]
    assert after_convert["modified_kwargs"]["set_reply"] is False
    assert after_message["reply_to"] == "inbound-1"
    assert after_convert["modified_kwargs"]["reply_message_id"] == "inbound-1"
    assert after_convert["modified_kwargs"]["route_metadata"] == {"source": "normal-reply"}
    assert [item["type"] for item in after_message["raw_message"]] == ["voice"]
    assert after_message["message_info"]["additional_config"]["silver_dragon_voice_delivery"]
    restored = deserialize_session_message(after_message)
    assert restored.processed_plain_text == answer
    assert restored.raw_message.components[0].content == answer
    assert [item["type"] for item in NapCatOutboundSegmentEncoder().convert_segments(after_message["raw_message"])] == ["record"]

    # 先清理引用再转语音：内部 target 仍可用于同一条动态请求，不会串到别的消息。
    plugin, synthesize = await _prepared_dynamic_plugin(answer)
    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    before_direct = await plugin.force_direct_qq_send(
        message=_dynamic_outbound(answer), typing=False, set_reply=True, reply_message_id="inbound-1",
        storage_message=True, show_log=True,
    )
    converted_after_direct = await plugin.convert_reply_to_voice(**before_direct["modified_kwargs"])
    final_message = converted_after_direct["modified_kwargs"]["message"]
    assert converted_after_direct["modified_kwargs"]["set_reply"] is False
    assert final_message["reply_to"] == "inbound-1"
    assert [item["type"] for item in final_message["raw_message"]] == ["voice"]
