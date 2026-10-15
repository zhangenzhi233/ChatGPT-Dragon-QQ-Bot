"""主动任务回执持久化与回合归属；不运行模型或平台发送。"""

from types import SimpleNamespace
import json

import pytest

from src.maisaka import proactive_receipts as module
from src.maisaka.proactive_receipts import ReceiptStore


def store_at(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.json")
    store.queue("proactive:p:t1", "p", "s")
    return store


def result(store):
    return store.get("proactive:p:t1", "p", "s")


def test_queued_does_not_mean_delivered_and_scope_is_enforced(tmp_path):
    store = store_at(tmp_path)
    assert result(store)["status"] == "queued"
    assert store.get("proactive:p:t1", "other-plugin", "s") is None
    assert store.get("proactive:p:t1", "p", "other-stream") is None


def test_all_segments_confirmed_is_delivered_and_not_rewritable(tmp_path):
    store = store_at(tmp_path)
    offset = store.plan("proactive:p:t1", "s", 2)
    for i in range(2):
        store.segment("proactive:p:t1", "s", offset + i)
        store.segment("proactive:p:t1", "s", offset + i, sent=True, message_id=f"qq-{i}")
    store.finish("proactive:p:t1", "s")
    assert result(store)["status"] == "delivered"
    store.finish("proactive:p:t1", "s", outcome="failed")
    store.segment("proactive:p:t1", "s", 0, sent=False)
    assert result(store)["status"] == "delivered"
    assert ReceiptStore(store.path).get("proactive:p:t1", "p", "s")["status"] == "delivered"


@pytest.mark.parametrize("confirmed,expected", [(0, "unknown"), (1, "partial")])
def test_lost_receipt_or_split_interruption_is_never_complete(tmp_path, confirmed, expected):
    store = store_at(tmp_path)
    store.plan("proactive:p:t1", "s", 2)
    if confirmed:
        store.segment("proactive:p:t1", "s", 0, sent=True)
    store.segment("proactive:p:t1", "s", confirmed)
    store.finish("proactive:p:t1", "s", outcome="failed")
    assert result(store)["status"] == expected


@pytest.mark.parametrize("outcome,expected", [("finished", "no_reply"), ("failed", "failed"), ("superseded", "superseded")])
def test_no_send_does_not_count_as_contact(tmp_path, outcome, expected):
    store = store_at(tmp_path)
    store.finish("proactive:p:t1", "s", outcome=outcome)
    assert result(store)["status"] == expected


def test_restart_keeps_uncertainty_and_does_not_replay(tmp_path):
    store = store_at(tmp_path)
    store.plan("proactive:p:t1", "s", 1)
    store.segment("proactive:p:t1", "s", 0)
    restarted = ReceiptStore(store.path)
    assert restarted.get("proactive:p:t1", "p", "s")["status"] == "unknown"
    assert len(json.loads(store.path.read_text(encoding="utf-8"))["tasks"]) == 1


def test_bad_ledger_blocks_queue_instead_of_resetting(tmp_path):
    store = ReceiptStore(tmp_path / "receipts.json")
    store.path.write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError):
        store.queue("t1", "p", "s")
    assert store.path.read_text(encoding="utf-8") == "{bad"


def test_failed_or_completed_reply_cannot_be_replayed(tmp_path):
    store = store_at(tmp_path)
    store.plan("proactive:p:t1", "s", 1)
    store.segment("proactive:p:t1", "s", 0, sent=True)
    with pytest.raises(ValueError):
        store.plan("proactive:p:t1", "s", 1)
    # 不同类型的后续附件动作可追加，但任何不明动作都会阻止再次进入发送。
    assert store.plan("proactive:p:t1", "s", 1, action="send_emoji") == 1
    store.segment("proactive:p:t1", "s", 1)
    with pytest.raises(ValueError):
        store.plan("proactive:p:t1", "s", 1, action="send_image")


@pytest.mark.asyncio
async def test_media_delivery_uses_same_ledger_and_does_not_replay(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from src.core.tooling import ToolExecutionResult

    store = store_at(tmp_path)
    monkeypatch.setattr(module, "receipts", store)
    runtime = SimpleNamespace(session_id="s", _active_proactive_task_id="proactive:p:t1", _has_pending_messages=lambda: False)
    registry = SimpleNamespace(invoke=AsyncMock(return_value=ToolExecutionResult(tool_name="send_emoji", success=True)))
    invocation = SimpleNamespace(tool_name="send_emoji")
    assert (await module.invoke_tracked_media(runtime, registry, invocation, None)).success
    assert not (await module.invoke_tracked_media(runtime, registry, invocation, None)).success
    assert registry.invoke.await_count == 1
    module.finish_runtime_task(runtime)
    assert result(store)["status"] == "delivered"


@pytest.mark.asyncio
async def test_engine_marks_silent_proactive_turn_and_clears_attribution(tmp_path, monkeypatch):
    from src.maisaka.reasoning_engine import MaisakaReasoningEngine, TurnStartContext

    store = store_at(tmp_path)
    monkeypatch.setattr(module, "receipts", store)
    runtime = SimpleNamespace(session_id="s", log_prefix="test", _max_internal_rounds=0,
                              _consume_forced_turn_reason=lambda: "")
    engine = MaisakaReasoningEngine(runtime)
    engine._finalize_turn = lambda: None
    await engine._run_active_turn(TurnStartContext([], SimpleNamespace(message_id="proactive:p:t1"), False, True, False))
    assert result(store)["status"] == "no_reply"
    assert runtime._active_proactive_task_id is None


@pytest.mark.asyncio
async def test_engine_failure_before_send_is_not_sent(tmp_path, monkeypatch):
    from src.maisaka.reasoning_engine import MaisakaReasoningEngine, TurnStartContext

    store = store_at(tmp_path)
    monkeypatch.setattr(module, "receipts", store)

    def fail():
        raise RuntimeError("offline model failure")

    runtime = SimpleNamespace(session_id="s", log_prefix="test", _max_internal_rounds=1, _consume_forced_turn_reason=fail)
    engine = MaisakaReasoningEngine(runtime)
    engine._finalize_turn = lambda: None
    with pytest.raises(RuntimeError):
        await engine._run_active_turn(TurnStartContext([], SimpleNamespace(message_id="proactive:p:t1"), False, True, False))
    assert result(store)["status"] == "failed"
    assert runtime._active_proactive_task_id is None


@pytest.mark.asyncio
async def test_status_capability_only_reads_callers_tasks(tmp_path, monkeypatch):
    from src.plugin_runtime.capabilities.core import RuntimeCoreCapabilityMixin

    store = store_at(tmp_path)
    monkeypatch.setattr(module, "receipts", store)
    api = RuntimeCoreCapabilityMixin()
    args = {"task_id": "proactive:p:t1", "stream_id": "s"}
    assert (await api._cap_maisaka_proactive_status("p", "", args))["receipt"]["status"] == "queued"
    assert (await api._cap_maisaka_proactive_status("other", "", args))["receipt"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,expected,count", [("ok", "delivered", 2), ("lost", "partial", 2), ("new-message", "partial", 1), ("before-send", "superseded", 0)])
async def test_real_reply_handler_tracks_segments_and_stops_on_new_input(tmp_path, monkeypatch, mode, expected, count):
    from unittest.mock import AsyncMock
    from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
    from src.maisaka.builtin_tool import reply

    store = store_at(tmp_path)
    monkeypatch.setattr(module, "receipts", store)
    monkeypatch.setattr(reply.config_module.global_config.experimental, "enable_rich_reply", False)
    monkeypatch.setattr(reply, "build_reply_monitor_detail", lambda result: {})
    target = SimpleNamespace(message_info=SimpleNamespace(user_info=SimpleNamespace(user_id="u", user_nickname="user", user_cardname="")))
    calls = []
    pending = [mode == "before-send"]
    runtime = SimpleNamespace(
        session_id="s", log_prefix="test", _active_proactive_task_id="proactive:p:t1", _chat_history=[],
        chat_stream=SimpleNamespace(platform="qq", is_group_session=False),
        find_source_message_by_id=lambda key: target, _update_stage_status=lambda *args: None,
        _has_pending_messages=lambda: pending[0],
    )
    generated = SimpleNamespace(completion=SimpleNamespace(response_text="第一段。第二段。"), monitor_detail={},
                                selected_expression_ids=[], error_message="")
    replyer = SimpleNamespace(generate_reply_with_context=AsyncMock(return_value=(True, generated)))
    monkeypatch.setattr(reply.replyer_manager, "get_replyer", lambda **kwargs: replyer)
    monkeypatch.setattr(reply, "_invoke_before_post_process_hook", AsyncMock(return_value=("第一段。第二段。", {})))
    items = [SimpleNamespace(sequence=MessageSequence([TextComponent(text)]), quote_previous=False)
             for text in ("第一段。", "第二段。")]
    tool_ctx = SimpleNamespace(
        runtime=runtime, post_process_reply_message_items_async=AsyncMock(return_value=items),
        record_sent_reply_emoji_usage=lambda seq: None,
        build_failure_result=lambda *args, **kwargs: SimpleNamespace(success=False),
        build_success_result=lambda *args, **kwargs: SimpleNamespace(success=True),
    )

    async def send(**kwargs):
        calls.append(kwargs)
        if mode == "new-message":
            pending[0] = True
        if mode == "lost" and len(calls) == 2:
            raise RuntimeError("platform accepted but receipt lost")
        return SimpleNamespace(message_id=f"qq-{len(calls)}")

    monkeypatch.setattr(reply.send_service, "_send_to_target_with_message", send)
    invocation = SimpleNamespace(arguments={"msg_id": "u1", "set_quote": False}, reasoning="r", call_id="c", tool_name="reply")
    outcome = await reply.handle_tool(tool_ctx, invocation)
    module.finish_runtime_task(runtime)
    assert len(calls) == count
    assert result(store)["status"] == expected
    assert outcome.success == (mode == "ok")
    assert all(call["stream_id"] == "s" for call in calls)
