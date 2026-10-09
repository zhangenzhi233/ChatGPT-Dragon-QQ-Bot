"""调度器集成测试：用真实 SDK + 模拟 transport/LLM，覆盖验收点。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncio
import json
import logging
import time

from helpers import (
    MAIN_QQ,
    MockTransport,
    build_message,
    build_stream,
    chat_response,
    make_plugin,
    silence_response,
)

from SilverDragonCompanion.policy import BEIJING_TZ
from SilverDragonCompanion.scheduler import CompanionScheduler
from SilverDragonCompanion.state import CompanionState, StateStore

LOGGER = logging.getLogger("test.scheduler")


def _state_path(tmp_path):
    return tmp_path / "data" / "plugins" / "local.silver-dragon-companion" / "companion-state.json"


def _poll(plugin) -> None:
    """单步执行一次调度轮询（每次用新调度器，避免跨事件循环锁复用）。"""
    scheduler = CompanionScheduler(plugin, LOGGER)
    asyncio.run(scheduler._poll_once())  # noqa: SLF001 - 白盒单步测试


def _write_startup(runtime_dir, request_id: str = "g1") -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "startup-request.json").write_text(
        json.dumps({"request_id": request_id, "requested_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )


def _load_state(ctx) -> CompanionState:
    state, ok = StateStore(ctx.paths.data_dir, LOGGER).load(MAIN_QQ)
    assert ok is True and state is not None
    return state


def _llm_call_count(transport: MockTransport) -> int:
    return len([c for c in transport.calls if c[0] == "llm.generate"])


def test_startup_signal_queues_and_records_queued_not_sent(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    plugin, ctx = make_plugin(transport, tmp_path)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)

    calls = transport.proactive_calls()
    assert len(calls) == 1
    assert "天气" in calls[0]["intent"]
    state = _load_state(ctx)
    assert any(record.status == "queued" for record in state.attempts.values())
    # queued 绝不冒充 sent
    assert all(record.status != "sent" for record in state.attempts.values())


def test_startup_signal_dedup_no_double_evaluation(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    plugin, ctx = make_plugin(transport, tmp_path)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    _poll(plugin)  # 信号已消费，且 next_check 在未来，不应再次评估
    assert len(transport.proactive_calls()) == 1
    assert _llm_call_count(transport) == 1


def test_model_silence_sets_next_without_trigger(tmp_path):
    transport = MockTransport()
    transport.llm_response = silence_response(200)
    plugin, ctx = make_plugin(transport, tmp_path)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    assert transport.proactive_calls() == []
    state = _load_state(ctx)
    assert state.next_check_at is not None


def test_variable_next_time_reflected_in_state(tmp_path, monkeypatch):
    transport = MockTransport()
    plugin, ctx = make_plugin(transport, tmp_path)

    transport.llm_response = silence_response(30)
    _write_startup(ctx.paths.runtime_dir, "a")
    _poll(plugin)
    first = _load_state(ctx)

    later = datetime.fromisoformat(first.last_startup_at) + timedelta(minutes=16)
    monkeypatch.setattr("SilverDragonCompanion.scheduler.beijing_now", lambda: later)

    transport.llm_response = silence_response(300)
    _write_startup(ctx.paths.runtime_dir, "b")
    _poll(plugin)
    second = _load_state(ctx)

    assert first.next_check_at != second.next_check_at


def test_group_stream_rejected_no_trigger(tmp_path):
    transport = MockTransport()
    transport.stream = build_stream(group=True)
    transport.llm_response = chat_response("天气")
    plugin, ctx = make_plugin(transport, tmp_path)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    assert transport.proactive_calls() == []


def test_disabled_plugin_no_action(tmp_path):
    transport = MockTransport()
    plugin, ctx = make_plugin(transport, tmp_path, enabled=False)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    assert transport.calls == []


def test_empty_main_qq_rejects(tmp_path):
    transport = MockTransport()
    plugin, ctx = make_plugin(transport, tmp_path, main_qq="")
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    assert transport.proactive_calls() == []


def test_new_chat_during_decision_marks_skipped(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    now = time.time()
    # 决策快照看到的主号最后消息在 10 分钟前
    transport.messages = [build_message(text="早", from_user=True, ts=now - 600, message_id="u0")]
    # 复核时发现 3 分钟前出现新的主号消息 → 决策过期
    transport.recent_messages = [build_message(text="在吗", from_user=True, ts=now - 180, message_id="u1")]
    plugin, ctx = make_plugin(transport, tmp_path)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    assert transport.proactive_calls() == []
    state = _load_state(ctx)
    assert any(record.status == "skipped" for record in state.attempts.values())


def test_attempt_persisted_before_trigger(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    captured: dict[str, str] = {}
    original = transport.rpc_call

    async def custom_rpc(method, plugin_id, payload, timeout_ms=None):
        if payload.get("capability") == "maisaka.proactive.trigger":
            raw = json.loads(_state_path(tmp_path).read_text(encoding="utf-8"))
            record = next(iter(raw["attempts"].values()))
            captured["status_at_trigger"] = record["status"]
        return await original(method, plugin_id, payload, timeout_ms)

    transport.rpc_call = custom_rpc
    plugin, ctx = make_plugin(transport, tmp_path)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    # attempt 在 trigger 被调用前已落盘为 pending
    assert captured["status_at_trigger"] == "pending"


def test_crash_during_trigger_no_resend_after_restart(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    transport.proactive_error = RuntimeError("boom")
    plugin, ctx = make_plugin(transport, tmp_path)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    state = _load_state(ctx)
    assert any(record.status == "unknown" for record in state.attempts.values())

    # 模拟重启：新插件/调度器，状态仍在；信号已消费且 next_check 在未来 → 不重发
    transport2 = MockTransport()
    transport2.llm_response = chat_response("天气")
    plugin2, _ctx2 = make_plugin(transport2, tmp_path)
    _poll(plugin2)
    assert transport2.proactive_calls() == []


def test_corrupt_state_no_send(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    plugin, ctx = make_plugin(transport, tmp_path)
    _state_path(tmp_path).write_text("{broken json", encoding="utf-8")
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    assert transport.proactive_calls() == []
    assert _llm_call_count(transport) == 0


def test_daily_cap_no_trigger(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    plugin, ctx = make_plugin(transport, tmp_path)
    now = datetime.now(BEIJING_TZ)
    StateStore(ctx.paths.data_dir, LOGGER).save(
        CompanionState(
            main_qq=MAIN_QQ,
            next_check_at=(now - timedelta(seconds=1)).isoformat(),
            trigger_day=now.strftime("%Y-%m-%d"),
            trigger_count_today=3,
        )
    )
    _poll(plugin)
    assert transport.proactive_calls() == []
    assert _llm_call_count(transport) == 0


def test_min_trigger_interval_blocks_trigger(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    plugin, ctx = make_plugin(transport, tmp_path)
    now = datetime.now(BEIJING_TZ)
    StateStore(ctx.paths.data_dir, LOGGER).save(
        CompanionState(
            main_qq=MAIN_QQ,
            next_check_at=(now - timedelta(seconds=1)).isoformat(),
            last_trigger_at=(now - timedelta(minutes=10)).isoformat(),
        )
    )
    _poll(plugin)
    assert transport.proactive_calls() == []


def test_silent_hours_no_trigger(monkeypatch, tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    plugin, ctx = make_plugin(transport, tmp_path)
    fixed_now = datetime(2026, 10, 8, 3, 0, tzinfo=BEIJING_TZ)
    monkeypatch.setattr("SilverDragonCompanion.scheduler.beijing_now", lambda: fixed_now)
    StateStore(ctx.paths.data_dir, LOGGER).save(
        CompanionState(main_qq=MAIN_QQ, next_check_at=(fixed_now - timedelta(seconds=1)).isoformat())
    )
    _poll(plugin)
    assert transport.proactive_calls() == []
    assert _llm_call_count(transport) == 0


def test_startup_recent_chat_silence(tmp_path):
    transport = MockTransport()
    transport.llm_response = chat_response("天气")
    now = time.time()
    transport.messages = [build_message(text="刚聊过", from_user=True, ts=now - 60, message_id="u0")]
    plugin, ctx = make_plugin(transport, tmp_path)
    _write_startup(ctx.paths.runtime_dir)
    _poll(plugin)
    assert transport.proactive_calls() == []
    assert _llm_call_count(transport) == 0


def test_stop_cancels_task(tmp_path):
    transport = MockTransport()
    plugin, _ctx = make_plugin(transport, tmp_path)
    scheduler = CompanionScheduler(plugin, LOGGER)

    async def scenario():
        await scheduler.start()
        assert scheduler._task is not None  # noqa: SLF001
        await scheduler.stop()
        assert scheduler._task is None  # noqa: SLF001

    asyncio.run(scenario())
