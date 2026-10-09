import asyncio
import re
from types import SimpleNamespace

import pytest
from maibot_sdk.context import PluginContext

import plugins.SilverDragonVoice.plugin as voice_plugin
from plugins.SilverDragonVoice.plugin import SilverDragonVoicePlugin


class FakeSend:
    def __init__(self, result=True):
        self.result = result
        self.hybrid_calls = []
        self.text_calls = []

    async def hybrid(self, segments, stream_id, **kwargs):
        self.hybrid_calls.append((segments, stream_id, kwargs))
        return self.result

    async def text(self, text, stream_id, **kwargs):
        self.text_calls.append((text, stream_id, kwargs))
        return True


class FakeChat:
    _DEFAULT = object()

    def __init__(self, result=_DEFAULT):
        # 模拟 SDK 代理的返回值，而不是宿主原始 RPC 包装。
        self.result = result if result is not self._DEFAULT else {
            "stream_id": "current-stream",
            "platform": "qq",
            "user_id": "10001",
            "group_id": "",
            "is_group_session": False,
            "chat_type": "private",
        }

    async def get_stream_by_user_id(self, user_id, platform):
        return self.result


def build_plugin(*, enabled=True, allowed_users=None, send_result=True):
    plugin = SilverDragonVoicePlugin()
    plugin.set_plugin_config(
        {
            "plugin": {"enabled": enabled, "config_version": "1.0.0"},
            "voice": {
                "voice": "zh-CN-XiaoxiaoNeural",
                "rate": "-6%",
                "pitch": "+8Hz",
                "timeout_seconds": 1,
                "max_length": 200,
            },
            "access": {"allowed_user_ids": allowed_users if allowed_users is not None else ["10001"]},
        }
    )
    send = FakeSend(send_result)
    plugin._set_context(
        SimpleNamespace(send=send, chat=FakeChat(), logger=SimpleNamespace(
            warning=lambda *args, **kwargs: None, info=lambda *args, **kwargs: None
        ))
    )
    return plugin, send


def current_private_request(**overrides):
    request = {"platform": "qq", "group_id": "", "stream_id": "current-stream", "user_id": "10001"}
    request.update(overrides)
    return request


async def invoke_voice_command(plugin, text, **request):
    return await plugin.send_voice_command(matched_groups={"text": text}, **request)


@pytest.mark.asyncio
async def test_authorized_private_request_sends_base64_voice(monkeypatch):
    plugin, send = build_plugin()

    async def synthesize(text):
        assert text == "你好"
        return b"mock-mp3"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    result = await invoke_voice_command(plugin, "你好", **current_private_request())

    assert result == (True, None, True)
    segments, stream_id, kwargs = send.hybrid_calls[0]
    assert segments == [{"type": "voice", "content": "bW9jay1tcDM="}]
    assert stream_id == "current-stream"
    assert kwargs == {"return_details": True, "set_reply": False}


@pytest.mark.asyncio
async def test_private_lookup_uses_real_sdk_result_normalization(monkeypatch):
    plugin, send = build_plugin()
    calls = []

    async def rpc_call(method, plugin_id, payload):
        calls.append((method, payload))
        assert payload["capability"] == "chat.get_stream_by_user_id"
        return {"success": True, "stream": FakeChat().result}

    plugin.ctx.chat = PluginContext("local.silver-dragon-voice", rpc_call=rpc_call).chat

    async def synthesize(text):
        return b"sdk-checked-mp3"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    result = await invoke_voice_command(plugin, "你好", **current_private_request())
    assert result == (True, None, True)
    assert len(calls) == 1 and len(send.hybrid_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("host_result", [
    {"success": False, "error": "lookup failed"},
    {"success": True, "stream": None},
])
async def test_real_sdk_failed_lookup_never_sends_voice(monkeypatch, host_result):
    plugin, send = build_plugin()

    async def rpc_call(method, plugin_id, payload):
        return host_result

    plugin.ctx.chat = PluginContext("local.silver-dragon-voice", rpc_call=rpc_call).chat
    monkeypatch.setattr(plugin, "_synthesize", lambda text: b"must-not-run")
    result = await invoke_voice_command(plugin, "你好", **current_private_request())
    assert result[0] is False and "无法核验" in result[1]
    assert send.hybrid_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        current_private_request(group_id="123"),
        current_private_request(platform="telegram"),
        current_private_request(user_id="20002"),
    ],
)
async def test_rejects_non_private_or_unauthorized_request(monkeypatch, context):
    plugin, send = build_plugin()
    monkeypatch.setattr(plugin, "_synthesize", lambda text: b"must-not-run")

    result = await invoke_voice_command(plugin, "你好", **context)

    assert result[0] is False
    assert not send.hybrid_calls


@pytest.mark.asyncio
async def test_empty_authorization_list_denies_all(monkeypatch):
    plugin, send = build_plugin(allowed_users=[])
    monkeypatch.setattr(plugin, "_synthesize", lambda text: b"must-not-run")

    result = await invoke_voice_command(plugin, "你好", **current_private_request())

    assert result[0] is False
    assert "未获授权" in result[1]
    assert not send.hybrid_calls


@pytest.mark.asyncio
async def test_rejects_when_resolved_private_stream_does_not_match(monkeypatch):
    plugin, send = build_plugin()
    plugin.ctx.chat = FakeChat(
        {
            "stream_id": "other-stream", "platform": "qq", "user_id": "10001", "chat_type": "private",
        }
    )
    monkeypatch.setattr(plugin, "_synthesize", lambda text: b"must-not-run")

    result = await invoke_voice_command(plugin, "你好", **current_private_request())

    assert result[0] is False
    assert not send.hybrid_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, {"success": False}, {"success": True, "stream": None}])
async def test_rejects_failed_or_missing_stream_lookup(monkeypatch, result):
    plugin, send = build_plugin()
    plugin.ctx.chat = FakeChat(result)
    monkeypatch.setattr(plugin, "_synthesize", lambda text: b"must-not-run")

    response = await invoke_voice_command(plugin, "你好", **current_private_request())

    assert response[0] is False
    assert not send.hybrid_calls


@pytest.mark.asyncio
async def test_timeout_and_send_failure_do_not_retry(monkeypatch):
    plugin, send = build_plugin()

    async def timeout_synthesis(text):
        raise TimeoutError

    monkeypatch.setattr(plugin, "_synthesize", timeout_synthesis)
    timeout_result = await invoke_voice_command(plugin, "你好", **current_private_request())
    assert timeout_result[0] is False
    assert not send.hybrid_calls

    plugin, send = build_plugin(send_result={"sent": False})

    async def synthesize(text):
        return b"mock-mp3"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    failed_send = await invoke_voice_command(plugin, "再试一次", **current_private_request())
    assert failed_send[0] is False
    assert len(send.hybrid_calls) == 1


@pytest.mark.asyncio
async def test_duplicate_request_and_configurable_voice(monkeypatch):
    plugin, send = build_plugin()
    plugin.set_plugin_config(
        {
            **plugin.get_plugin_config_data(),
            "voice": {
                **plugin.get_plugin_config_data()["voice"],
                "voice": "zh-CN-XiaoyiNeural",
                "rate": "+5%",
                "pitch": "+2Hz",
            },
        }
    )
    assert plugin.config.voice.voice == "zh-CN-XiaoyiNeural"

    communicate_args = {}

    class FakeCommunicate:
        def __init__(self, **kwargs):
            communicate_args.update(kwargs)

        async def stream(self):
            yield {"type": "audio", "data": b"configured-mp3"}

    monkeypatch.setattr("plugins.SilverDragonVoice.plugin.edge_tts.Communicate", FakeCommunicate)
    assert await plugin._synthesize("参数测试") == b"configured-mp3"
    assert communicate_args == {
        "text": "参数测试",
        "voice": "zh-CN-XiaoyiNeural",
        "rate": "+5%",
        "pitch": "+2Hz",
    }

    async def synthesize(text):
        return b"mock-mp3"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    first = await invoke_voice_command(plugin, "同一句", **current_private_request())
    duplicate = await invoke_voice_command(plugin, "同一句", **current_private_request())

    assert first[0] is True
    assert duplicate[0] is False
    assert "重复" in duplicate[1]
    assert len(send.hybrid_calls) == 1


@pytest.mark.asyncio
async def test_pending_request_stays_deduplicated_past_cooldown_window(monkeypatch):
    plugin, send = build_plugin()
    now = [0.0]
    started = asyncio.Event()
    finish = asyncio.Event()
    monkeypatch.setattr(voice_plugin, "monotonic", lambda: now[0])

    async def blocked_synthesis(text):
        started.set()
        await finish.wait()
        return b"mock-mp3"

    monkeypatch.setattr(plugin, "_synthesize", blocked_synthesis)
    first_task = asyncio.create_task(invoke_voice_command(plugin, "并发内容", **current_private_request()))
    await started.wait()
    now[0] = plugin._DEDUP_WINDOW_SECONDS + 1

    duplicate = await invoke_voice_command(plugin, "并发内容", **current_private_request())
    assert duplicate[0] is False
    assert "重复" in duplicate[1]
    assert not send.hybrid_calls

    finish.set()
    first = await first_task
    assert first[0] is True
    assert len(send.hybrid_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase",
    [
        "用语音回复我",
        "  让我听听你的声音！  ",
        "请用语音回复我？",
        "发条语音给我。",
        "我可以听听你说话的声音吗",
        "我可以听听你说话的声音吗？",
        "能用语音回复吗",
        "你能不能给我发一条语音？",
        "可以让我听听你的声音吗",
        "我想听听你的声音",
        "我给你添加了语言的功能，看看你说话效果怎么样",
        "我给你添加了语音的功能，看看你说话效果怎么样",
        "试试新声音吧",
        "我想听你的声音",
        "可以发送语音吗",
        "可以发送语言吗",
        "我修复了原来的问题，现在试试语音效果",
        "我修复了原来的语音识别问题，现在试试语音效果吧",
    ],
)
async def test_natural_voice_requests_continue_normal_chat(phrase):
    plugin, send = build_plugin()
    greeting_component = next(component for component in plugin.get_components() if component["name"] == "voice_greeting")
    pattern = greeting_component["metadata"]["command_pattern"]
    assert pattern == r"^/试听$"
    assert re.search(pattern, phrase) is None
    result = await plugin.send_voice_greeting(text=phrase, **current_private_request())
    assert result == (True, None, False)
    assert send.hybrid_calls == []
    assert send.text_calls == []


@pytest.mark.asyncio
async def test_explicit_preview_alone_reads_fixed_greeting(monkeypatch):
    plugin, send = build_plugin()

    async def synthesize(text):
        assert text == plugin.config.voice.greeting_text
        return b"greeting-mp3"

    monkeypatch.setattr(plugin, "_synthesize", synthesize)
    result = await plugin.send_voice_greeting(text="/试听", **current_private_request())
    assert result == (True, None, True)
    assert len(send.hybrid_calls) == 1
    assert send.text_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase",
    [
        "不要用语音回复我",
        "我不想听听你的声音",
        "如果我说让我听听你的声音，你会怎么办",
        "她问我可以听听你说话的声音吗",
        "“我可以听听你说话的声音吗”这句话怎么翻译",
        "你的声音听起来好可爱",
    ],
)
async def test_voice_discussion_negation_and_quotes_continue_normal_chat(phrase):
    plugin, send = build_plugin()
    result = await plugin.send_voice_greeting(text=phrase, **current_private_request())
    assert result == (True, None, False)
    assert send.hybrid_calls == []
    assert send.text_calls == []


def test_does_not_register_a_voice_sending_tool():
    plugin, _send = build_plugin()
    components = plugin.get_components()
    assert all(component["type"] != "TOOL" for component in components)
    assert "send_silver_dragon_voice" not in {component["name"] for component in components}


@pytest.mark.asyncio
async def test_lifecycle_hooks_are_safe_and_unload_clears_dedup_state(tmp_path):
    plugin, _send = build_plugin()
    plugin.ctx.paths = SimpleNamespace(runtime_dir=tmp_path)
    plugin._pending_requests.add("pending")
    plugin._recent_requests["recent"] = 1.0

    assert await plugin.on_load() is None
    diagnosis = (tmp_path / "voice-readiness.json").read_text(encoding="utf-8")
    assert '"sdk_lookup_returns_verified_stream": true' in diagnosis
    assert '"replyer_note_with_real_sdk_verified": true' in diagnosis
    assert '"voice_convert_reply"' in diagnosis
    assert "10001" not in diagnosis and "current-stream" not in diagnosis
    assert _send.hybrid_calls == [] and _send.text_calls == []
    assert await plugin.on_unload() is None
    assert plugin._pending_requests == set()
    assert plugin._recent_requests == {}


@pytest.mark.asyncio
async def test_load_diagnosis_does_not_mark_missing_session_ready(tmp_path):
    plugin, send = build_plugin()
    plugin.ctx.paths = SimpleNamespace(runtime_dir=tmp_path)
    plugin.ctx.chat = FakeChat(None)
    await plugin.on_load()
    diagnosis = (tmp_path / "voice-readiness.json").read_text(encoding="utf-8")
    assert '"sdk_lookup_returns_verified_stream": false' in diagnosis
    assert '"replyer_note_with_real_sdk_verified": false' in diagnosis
    assert send.hybrid_calls == [] and send.text_calls == []


@pytest.mark.asyncio
async def test_self_config_update_applies_new_voice_to_synthesis(monkeypatch):
    plugin, _send = build_plugin()
    updated_config = {
        **plugin.get_plugin_config_data(),
        "voice": {
            **plugin.get_plugin_config_data()["voice"],
            "voice": "zh-CN-YunxiNeural",
            "rate": "+10%",
            "pitch": "-4Hz",
        },
    }
    communicate_args = {}

    class FakeCommunicate:
        def __init__(self, **kwargs):
            communicate_args.update(kwargs)

        async def stream(self):
            yield {"type": "audio", "data": b"updated-mp3"}

    monkeypatch.setattr("plugins.SilverDragonVoice.plugin.edge_tts.Communicate", FakeCommunicate)
    assert await plugin.on_config_update("self", updated_config, "1.0.1") is None
    assert plugin.config.voice.voice == "zh-CN-YunxiNeural"
    assert await plugin._synthesize("热更新测试") == b"updated-mp3"
    assert communicate_args == {
        "text": "热更新测试",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+10%",
        "pitch": "-4Hz",
    }
