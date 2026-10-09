from copy import deepcopy

import pytest
from maibot_sdk.context import PluginContext

from plugins.SilverDragonVoice.plugin import VOICE_CAPABILITY_MARKER
from plugins.SilverDragonVoice.tests.test_plugin import FakeChat, build_plugin


@pytest.mark.asyncio
async def test_replyer_gets_current_voice_capability_without_losing_existing_prompt():
    plugin, send = build_plugin()
    payload = {
        "session_id": "current-stream", "extra_prompt": "保持原有角色风格。", "request_type": "reply",
        "reply_tool_args": {"text": "已经启用了语音功能"},
    }
    original = deepcopy(payload)
    result = await plugin.inject_replyer_voice_capability(**payload)

    assert result["action"] == "continue"
    updated = result["modified_kwargs"]
    assert updated["extra_prompt"].startswith(original["extra_prompt"])
    assert VOICE_CAPABILITY_MARKER in updated["extra_prompt"]
    assert "过期的错误说明" in updated["extra_prompt"]
    assert "普通问题的答案仍默认用文字回复" in updated["extra_prompt"]
    assert updated["reply_tool_args"] == original["reply_tool_args"]
    assert payload == original
    assert send.hybrid_calls == [] and send.text_calls == []

    # 在同一请求重入时避免追加重复说明。
    repeated = await plugin.inject_replyer_voice_capability(**updated)
    assert repeated == {"action": "continue"}


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled, allowed_users, session_id", [
    (False, ["10001"], "current-stream"),
    (True, [], "current-stream"),
    (True, ["10001"], "unrelated-stream"),
    (True, ["10001"], ""),
])
async def test_capability_note_is_scoped_to_enabled_authorized_private_session(enabled, allowed_users, session_id):
    plugin, send = build_plugin(enabled=enabled, allowed_users=allowed_users)
    result = await plugin.inject_replyer_voice_capability(
        session_id=session_id, extra_prompt="原提示", user_id="10001", stream_id="current-stream", platform="qq"
    )
    assert result == {"action": "continue"}
    assert send.hybrid_calls == [] and send.text_calls == []


@pytest.mark.asyncio
async def test_capability_note_rejects_group_and_bad_stream_lookup():
    plugin, _send = build_plugin()
    plugin.ctx.chat = FakeChat({
        "stream_id": "current-stream", "platform": "qq", "user_id": "10001",
        "group_id": "example-group", "is_group_session": True, "chat_type": "group",
    })
    assert await plugin.inject_replyer_voice_capability(session_id="current-stream") == {"action": "continue"}

    plugin.ctx.chat = FakeChat({"success": False})
    assert await plugin.inject_replyer_voice_capability(session_id="current-stream") == {"action": "continue"}


@pytest.mark.asyncio
async def test_replyer_authorization_passes_real_sdk_normalization():
    plugin, send = build_plugin()
    async def rpc_call(method, plugin_id, payload):
        assert payload["capability"] == "chat.get_stream_by_user_id"
        return {"success": True, "stream": FakeChat().result}

    plugin.ctx.chat = PluginContext("local.silver-dragon-voice", rpc_call=rpc_call).chat
    payload = {
        "session_id": "current-stream", "extra_prompt": "原要求", "reply_tool_args": {"text": "测试"},
    }
    result = await plugin.inject_replyer_voice_capability(**payload)
    updated = result["modified_kwargs"]
    assert VOICE_CAPABILITY_MARKER in updated["extra_prompt"]
    assert updated["reply_tool_args"] == payload["reply_tool_args"]
    assert send.hybrid_calls == [] and send.text_calls == []


def test_does_not_subscribe_to_planner_full_image_history():
    plugin, _send = build_plugin()
    names = {component["name"] for component in plugin.get_components()}
    assert "voice_replyer_capability" in names
    assert "voice_planner_capability" not in names
