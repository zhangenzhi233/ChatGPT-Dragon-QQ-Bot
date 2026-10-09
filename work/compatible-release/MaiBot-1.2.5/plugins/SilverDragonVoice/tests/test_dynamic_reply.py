from copy import deepcopy

import pytest
from maibot_sdk.context import PluginContext

from plugins.SilverDragonVoice.tests.test_plugin import build_plugin
from src.common.data_models.message_component_data_model import EmojiComponent, ImageComponent
from src.chat.message_receive.message import VoiceComponent
from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext, PreparedReplyAttachments
from src.maisaka.context.message_adapter import build_visible_text_from_sequence
from src.plugin_runtime.host.message_utils import PluginMessageUtils
from src.plugin_runtime.hook_payloads import deserialize_session_message
from src.services.send_service import _build_processed_plain_text, _prepare_message_for_platform_io


OWNER_ID = "10001"
STREAM_ID = "current-stream"


def message_payload(
    *,
    message_id: str,
    text: str,
    session_id: str = STREAM_ID,
    user_id: str = OWNER_ID,
    group_id: str = "",
    reply_to: str | None = None,
) -> dict:
    """构造与 Hook 边界一致的序列化 SessionMessage。"""

    return {
        "message_id": message_id,
        "timestamp": "0",
        "platform": "qq",
        "message_info": {
            "user_info": {"user_id": user_id, "user_nickname": "owner", "user_cardname": None},
            "group_info": {"group_id": group_id, "group_name": "group"} if group_id else None,
            "additional_config": {},
        },
        "raw_message": [{"type": "text", "data": text}],
        "session_id": session_id,
        "processed_plain_text": text,
        "reply_to": reply_to,
    }


def unchanged_raw_message(result: dict, original: dict) -> list[dict]:
    """Hook 不转换时可直接 continue，也可显式返回未修改的载荷。"""

    return result.get("modified_kwargs", {}).get("message", original)["raw_message"]


def install_message_lookup(plugin, message: dict) -> list[tuple[str, dict]]:
    """通过真实 SDK capability 解包，提供可信入站消息查询。"""

    calls: list[tuple[str, dict]] = []

    async def rpc_call(method, plugin_id, payload):
        del plugin_id
        calls.append((method, payload))
        assert method == "cap.call"
        assert payload["capability"] == "message.get_by_id"
        args = payload["args"]
        assert args["message_id"] == message["message_id"]
        assert args["stream_id"] == message["session_id"]
        assert args["include_binary_data"] is False
        return {"success": True, "message": message}

    plugin.ctx.message = PluginContext("local.silver-dragon-voice", rpc_call=rpc_call).message
    return calls


async def prepare_voice_reply(
    plugin, *, request: dict, answer: str, reply_message_id: str, expect_ready: bool = True
) -> dict:
    """通过可信入站消息和正常 Replyer 正文准备一次待转换语音。"""

    calls = install_message_lookup(plugin, request)
    request_result = await plugin.inject_replyer_voice_capability(
        session_id=request["session_id"],
        reply_message_id=reply_message_id,
        extra_prompt="",
    )
    assert request_result["action"] == "continue"
    assert calls
    result = await plugin.prepare_dynamic_reply(
        session_id=request["session_id"],
        reply_message_id=reply_message_id,
        response=answer,
        skip_post_process=False,
        enable_splitter=True,
        enable_chinese_typo=True,
        reply_tool_args={"origin": "normal-reply"},
    )
    assert result["action"] == "continue"
    if not expect_ready:
        assert "modified_kwargs" not in result
        return result
    prepared = result["modified_kwargs"]
    assert prepared["response"] == answer
    assert prepared["skip_post_process"] is True
    assert prepared["enable_splitter"] is False
    assert prepared["enable_chinese_typo"] is False
    assert prepared["reply_tool_args"] == {"origin": "normal-reply"}
    return prepared


@pytest.mark.asyncio
async def test_two_dynamic_answers_use_actual_reply_text_and_become_voice(monkeypatch):
    plugin, _send = build_plugin()
    synthesized = []

    async def synthesize(text):
        synthesized.append(text)
        return f"audio:{text}".encode()

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    cases = [
        ("owner-1", "我想听听你的声音，你今天怎么样？", "我今天状态很好，也想听听你的近况。"),
        ("owner-2", "能用语音回复吗？你会做什么？", "我可以陪你聊天、整理想法，也能按需用语音回答。"),
    ]
    converted_messages = []
    for message_id, question, answer in cases:
        request = message_payload(message_id=message_id, text=question)
        await prepare_voice_reply(plugin, request=request, answer=answer, reply_message_id=message_id)
        outbound = message_payload(message_id=f"reply-{message_id}", text=answer, reply_to=message_id)
        original = deepcopy(outbound)
        original_set_reply = message_id == "owner-1"
        converted = await plugin.convert_reply_to_voice(
            message=outbound,
            typing=False,
            set_reply=original_set_reply,
            reply_message_id=message_id,
            storage_message=True,
            show_log=True,
            route_metadata={"source": "normal-reply"},
        )
        assert converted["action"] == "continue"
        updated = converted["modified_kwargs"]
        assert updated["message"]["processed_plain_text"] == answer
        assert updated["set_reply"] is original_set_reply
        assert updated["typing"] is False
        assert updated["storage_message"] is True
        assert updated["show_log"] is True
        assert updated["route_metadata"] == {"source": "normal-reply"}
        assert original["processed_plain_text"] == answer
        converted_messages.append(deserialize_session_message(updated["message"]))

    assert synthesized == [case[2] for case in cases]
    assert synthesized != [plugin.config.voice.greeting_text] * 2
    for converted_message in converted_messages:
        assert len(converted_message.raw_message.components) == 1
        assert isinstance(converted_message.raw_message.components[0], VoiceComponent)
        assert converted_message.raw_message.components[0].content == converted_message.processed_plain_text
        assert converted_message.processed_plain_text in synthesized


@pytest.mark.asyncio
async def test_unrelated_messages_and_wrong_reply_id_keep_normal_text(monkeypatch):
    plugin, _send = build_plugin()
    synthesize_calls = []

    async def synthesize(text):
        synthesize_calls.append(text)
        return b"audio"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    request = message_payload(message_id="owner-1", text="让我听听你的声音")
    answer = "这是正常回答。"
    await prepare_voice_reply(plugin, request=request, answer=answer, reply_message_id="owner-1")

    unrelated = message_payload(message_id="reply-next", text="下一条普通回复。", reply_to="owner-1")
    unrelated_result = await plugin.convert_reply_to_voice(
        message=deepcopy(unrelated),
        typing=False,
        set_reply=True,
        reply_message_id="owner-1",
        storage_message=True,
        show_log=True,
    )
    assert unchanged_raw_message(unrelated_result, unrelated) == unrelated["raw_message"]

    wrong_id = message_payload(message_id="reply-wrong", text=answer, reply_to="owner-1")
    wrong_id_result = await plugin.convert_reply_to_voice(
        message=deepcopy(wrong_id),
        typing=False,
        set_reply=True,
        reply_message_id="owner-other",
        storage_message=True,
        show_log=True,
    )
    assert unchanged_raw_message(wrong_id_result, wrong_id) == wrong_id["raw_message"]
    assert synthesize_calls == []


@pytest.mark.asyncio
async def test_missing_or_mismatched_reply_id_never_uses_session_fallback(monkeypatch):
    plugin, _send = build_plugin()
    synthesize_calls = []

    async def synthesize(text):
        synthesize_calls.append(text)
        return b"audio"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    request = message_payload(message_id="owner-1", text="试试新声音吧")
    answer = "这是一段精确匹配的动态回答。"
    await prepare_voice_reply(plugin, request=request, answer=answer, reply_message_id="owner-1")

    missing = message_payload(message_id="reply-missing", text=answer)
    missing_result = await plugin.convert_reply_to_voice(
        message=deepcopy(missing),
        typing=False,
        set_reply=False,
        reply_message_id="",
        storage_message=True,
        show_log=True,
    )
    assert unchanged_raw_message(missing_result, missing) == missing["raw_message"]

    mismatched = message_payload(message_id="reply-mismatched", text=answer, reply_to="owner-1")
    mismatched_result = await plugin.convert_reply_to_voice(
        message=deepcopy(mismatched),
        typing=False,
        set_reply=True,
        reply_message_id="owner-other",
        storage_message=True,
        show_log=True,
    )
    assert unchanged_raw_message(mismatched_result, mismatched) == mismatched["raw_message"]
    assert synthesize_calls == []

    multi_text = message_payload(message_id="reply-multi", text=answer, reply_to="owner-1")
    multi_text["raw_message"].append({"type": "text", "data": "额外文字。"})
    multi_text_result = await plugin.convert_reply_to_voice(
        message=deepcopy(multi_text),
        typing=False,
        set_reply=True,
        reply_message_id="owner-1",
        storage_message=True,
        show_log=True,
    )
    assert unchanged_raw_message(multi_text_result, multi_text) == multi_text["raw_message"]


@pytest.mark.asyncio
async def test_duplicate_conversion_empty_long_and_failed_tts_keep_text(monkeypatch):
    plugin, _send = build_plugin()
    request = message_payload(message_id="owner-1", text="现在能发语音了吗")
    answer = "可转换的回答。"
    await prepare_voice_reply(plugin, request=request, answer=answer, reply_message_id="owner-1")
    calls = []

    async def synthesize(text):
        calls.append(text)
        return b"audio"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    outbound = message_payload(message_id="reply-1", text=answer, reply_to="owner-1")
    first = await plugin.convert_reply_to_voice(
        message=deepcopy(outbound), typing=False, set_reply=True, reply_message_id="owner-1", storage_message=True, show_log=True
    )
    second = await plugin.convert_reply_to_voice(
        message=deepcopy(outbound), typing=False, set_reply=True, reply_message_id="owner-1", storage_message=True, show_log=True
    )
    assert isinstance(deserialize_session_message(first["modified_kwargs"]["message"]).raw_message.components[0], VoiceComponent)
    assert unchanged_raw_message(second, outbound) == outbound["raw_message"]
    assert calls == [answer]

    for message_id, response in (("owner-empty", ""), ("owner-long", "超" * 201)):
        blocked_request = message_payload(message_id=message_id, text="让我听下你的声音")
        await prepare_voice_reply(
            plugin,
            request=blocked_request,
            answer=response,
            reply_message_id=message_id,
            expect_ready=bool(response),
        )
        untouched = message_payload(
            message_id=f"reply-{message_id}", text=response or "原始文字", reply_to=message_id
        )
        converted = await plugin.convert_reply_to_voice(
            message=deepcopy(untouched),
            typing=False,
            set_reply=True,
            reply_message_id=message_id,
            storage_message=True,
            show_log=True,
        )
        assert unchanged_raw_message(converted, untouched) == untouched["raw_message"]

    async def failing_synthesize(text):
        raise RuntimeError("offline failure")

    monkeypatch.setattr(plugin, "_synthesize", failing_synthesize)
    failed_request = message_payload(message_id="owner-fail", text="试试新声音吧")
    await prepare_voice_reply(plugin, request=failed_request, answer="合成失败时保留文字。", reply_message_id="owner-fail")
    failed_outbound = message_payload(
        message_id="reply-fail", text="合成失败时保留文字。", reply_to="owner-fail"
    )
    failed = await plugin.convert_reply_to_voice(
        message=deepcopy(failed_outbound),
        typing=False,
        set_reply=True,
        reply_message_id="owner-fail",
        storage_message=True,
        show_log=True,
    )
    assert unchanged_raw_message(failed, failed_outbound) == failed_outbound["raw_message"]


@pytest.mark.asyncio
async def test_delivery_observer_keeps_hook_flow_after_success_or_failure(monkeypatch):
    plugin, _send = build_plugin()

    async def synthesize(text):
        return b"audio"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    request = message_payload(message_id="owner-1", text="用语音回复我")
    answer = "这是一段会送达的正常回答。"
    await prepare_voice_reply(plugin, request=request, answer=answer, reply_message_id="owner-1")
    outbound = message_payload(message_id="reply-1", text=answer, reply_to="owner-1")
    converted = await plugin.convert_reply_to_voice(
        message=deepcopy(outbound),
        typing=False,
        set_reply=True,
        reply_message_id="owner-1",
        storage_message=True,
        show_log=True,
    )
    converted_message = converted["modified_kwargs"]["message"]
    assert await plugin.observe_voice_delivery(message=converted_message, sent=True) == {"action": "continue"}
    assert await plugin.observe_voice_delivery(message=converted_message, sent=False) == {"action": "continue"}


@pytest.mark.asyncio
async def test_voice_isolated_from_attachments_and_keeps_real_plain_text(monkeypatch):
    plugin, _send = build_plugin()

    async def synthesize(text):
        assert text == "这里是模型生成的正文。"
        return b"audio"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    request = message_payload(message_id="owner-1", text="让我听听你的声音")
    answer = "这里是模型生成的正文。"
    await prepare_voice_reply(plugin, request=request, answer=answer, reply_message_id="owner-1")
    outbound = message_payload(message_id="reply-1", text=answer, reply_to="owner-1")
    outbound["raw_message"] = [
        {"type": "image", "data": "配图说明", "hash": "image-hash"},
        {"type": "text", "data": answer},
        {"type": "emoji", "data": "表情说明", "hash": "emoji-hash"},
    ]
    original_message = deserialize_session_message(outbound)
    outbound["processed_plain_text"] = build_visible_text_from_sequence(original_message.raw_message).strip()
    assert "配图说明" in outbound["processed_plain_text"]
    assert "表情说明" in outbound["processed_plain_text"]
    converted = await plugin.convert_reply_to_voice(
        message=deepcopy(outbound),
        typing=False,
        set_reply=True,
        reply_message_id="owner-1",
        storage_message=True,
        show_log=True,
    )
    converted_message = deserialize_session_message(converted["modified_kwargs"]["message"])
    components = converted_message.raw_message.components
    assert [component.format_name for component in components] == ["voice"]
    assert isinstance(components[0], VoiceComponent)
    assert components[0].content == answer
    assert converted_message.processed_plain_text == answer
    assert _build_processed_plain_text(converted_message) == answer
    await _prepare_message_for_platform_io(
        converted_message,
        typing=False,
        set_reply=False,
        reply_message_id="owner-1",
    )
    assert converted_message.processed_plain_text == answer


@pytest.mark.asyncio
async def test_skip_post_process_keeps_parentheses_and_prepared_attachments(monkeypatch):
    """真实 Replyer 后处理仍会拼接附件，跳过仅保护模型正文不被改写。"""

    plugin, _send = build_plugin()
    answer = "（这是模型给出的完整回答）"
    request = message_payload(message_id="owner-1", text="用语音回复我，括号也请保留")
    prepared_kwargs = await prepare_voice_reply(
        plugin, request=request, answer=answer, reply_message_id="owner-1"
    )
    runtime_context = object.__new__(BuiltinToolRuntimeContext)
    attachments = PreparedReplyAttachments(
        image_components=[ImageComponent(binary_hash="image-hash", content="配图说明", binary_data=b"image")],
        emoji_components=[EmojiComponent(binary_hash="emoji-hash", content="表情说明", binary_data=b"emoji")],
    )
    items = await runtime_context.post_process_rich_reply_message_items_async(
        prepared_kwargs["response"],
        skip_post_process=prepared_kwargs["skip_post_process"],
        enable_splitter=prepared_kwargs["enable_splitter"],
        enable_chinese_typo=prepared_kwargs["enable_chinese_typo"],
        prepared_attachments=attachments,
    )
    assert len(items) == 1
    assert [item.format_name for item in items[0].sequence.components] == ["text", "image", "emoji"]
    assert items[0].sequence.components[0].text == answer

    synthesized = []

    async def synthesize(text):
        synthesized.append(text)
        return b"audio"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    outbound = message_payload(message_id="reply-1", text=answer, reply_to="owner-1")
    outbound["raw_message"] = [
        PluginMessageUtils._component_to_dict(component, include_binary_data=True)
        for component in items[0].sequence.components
    ]
    converted = await plugin.convert_reply_to_voice(
        message=outbound,
        typing=False,
        set_reply=True,
        reply_message_id="owner-1",
        storage_message=True,
        show_log=True,
    )
    converted_message = deserialize_session_message(converted["modified_kwargs"]["message"])
    assert synthesized == [answer]
    assert [component.format_name for component in converted_message.raw_message.components] == ["voice"]
    assert converted_message.raw_message.components[0].content == answer


@pytest.mark.asyncio
async def test_transient_stream_lookup_is_retried_before_post_process():
    """请求前的瞬态私聊查询失败不能永久屏蔽同一条正常回复。"""

    plugin, _send = build_plugin()
    request = message_payload(message_id="owner-1", text="让我听听你的声音")
    calls = install_message_lookup(plugin, request)

    class FlakyChat:
        def __init__(self):
            self.calls = 0

        async def get_stream_by_user_id(self, user_id, platform):
            assert (user_id, platform) == (OWNER_ID, "qq")
            self.calls += 1
            # 首次是 before_request 的授权核验；第二次为登记时的私聊复核。
            if self.calls == 2:
                raise RuntimeError("temporary lookup failure")
            return {
                "stream_id": STREAM_ID,
                "platform": "qq",
                "user_id": OWNER_ID,
                "group_id": "",
                "is_group_session": False,
                "chat_type": "private",
            }

    plugin.ctx.chat = FlakyChat()
    await plugin.inject_replyer_voice_capability(
        session_id=STREAM_ID, reply_message_id="owner-1", extra_prompt=""
    )
    prepared = await plugin.prepare_dynamic_reply(
        session_id=STREAM_ID,
        reply_message_id="owner-1",
        response="第二次查询成功后保留的正常回答。",
        skip_post_process=False,
        enable_splitter=True,
        enable_chinese_typo=True,
        reply_tool_args={},
    )
    assert len(calls) == 2
    assert plugin.ctx.chat.calls == 4
    assert prepared["modified_kwargs"]["skip_post_process"] is True


@pytest.mark.asyncio
async def test_whitespace_wrapped_allowed_user_id_can_prepare_voice_reply():
    plugin, _send = build_plugin(allowed_users=[" 10001 "])
    request = message_payload(message_id="owner-1", text="让我听听你的声音")
    prepared = await prepare_voice_reply(
        plugin,
        request=request,
        answer="白名单空白应被忽略。",
        reply_message_id="owner-1",
    )
    assert prepared["skip_post_process"] is True


@pytest.mark.asyncio
async def test_untrusted_user_group_or_session_never_records_convertible_request():
    plugin, _send = build_plugin()
    for payload in (
        message_payload(message_id="other-user", text="让我听听你的声音", user_id="20002"),
        message_payload(message_id="group", text="让我听听你的声音", group_id="group-1"),
        message_payload(message_id="other-session", text="让我听听你的声音", session_id="other-stream"),
    ):
        install_message_lookup(plugin, payload)
        assert (await plugin.inject_replyer_voice_capability(
            session_id=payload["session_id"], reply_message_id=payload["message_id"], extra_prompt=""
        ))["action"] == "continue"
        await plugin.prepare_dynamic_reply(
            session_id=payload["session_id"],
            reply_message_id=payload["message_id"],
            response="不应转换。",
            skip_post_process=False,
            enable_splitter=True,
            enable_chinese_typo=True,
            reply_tool_args={},
        )
        outbound = message_payload(
            message_id=f"reply-{payload['message_id']}", text="不应转换。",
            session_id=payload["session_id"], reply_to=payload["message_id"],
        )
        converted = await plugin.convert_reply_to_voice(
            message=deepcopy(outbound),
            typing=False,
            set_reply=True,
            reply_message_id=payload["message_id"],
            storage_message=True,
            show_log=True,
        )
        assert unchanged_raw_message(converted, outbound) == outbound["raw_message"]
