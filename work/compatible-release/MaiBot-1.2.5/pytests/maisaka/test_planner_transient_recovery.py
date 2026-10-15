"""Planner 瞬态失败有界恢复测试（不请求真实模型）。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio

import pytest

from src.llm_models.exceptions import (
    LLMTaskTimeoutError,
    ModelAttemptFailed,
    NetworkConnectionError,
    ReqAbortException,
    RespNotOkException,
)
from src.maisaka.reasoning_engine import CycleRuntimeState, MaisakaReasoningEngine


def _build_engine(*, pending_messages: bool = False) -> MaisakaReasoningEngine:
    runtime = SimpleNamespace(
        log_prefix="[test]",
        _running=True,
        _has_pending_messages=lambda: pending_messages,
    )
    return MaisakaReasoningEngine(runtime)


def _state() -> CycleRuntimeState:
    return CycleRuntimeState()


def test_transient_error_classification() -> None:
    assert MaisakaReasoningEngine._is_transient_planner_error(RespNotOkException(502))
    assert MaisakaReasoningEngine._is_transient_planner_error(RespNotOkException(500))
    assert MaisakaReasoningEngine._is_transient_planner_error(RespNotOkException(503))
    assert MaisakaReasoningEngine._is_transient_planner_error(NetworkConnectionError("网络中断"))
    assert MaisakaReasoningEngine._is_transient_planner_error(LLMTaskTimeoutError("planner", "model", 180))
    assert MaisakaReasoningEngine._is_transient_planner_error(ModelAttemptFailed("重试耗尽", NetworkConnectionError("y")))
    assert MaisakaReasoningEngine._is_transient_planner_error(ModelAttemptFailed("重试耗尽", RespNotOkException(503)))
    # 权限/额度错误不可重试。
    assert not MaisakaReasoningEngine._is_transient_planner_error(RespNotOkException(401))
    assert not MaisakaReasoningEngine._is_transient_planner_error(RespNotOkException(403))
    assert not MaisakaReasoningEngine._is_transient_planner_error(RespNotOkException(429))
    assert not MaisakaReasoningEngine._is_transient_planner_error(ValueError("未知错误"))


@pytest.mark.asyncio
async def test_recovery_retries_transient_once_then_succeeds() -> None:
    engine = _build_engine()
    calls: list[int] = []

    async def fake_request(**kwargs):
        del kwargs
        calls.append(1)
        if len(calls) == 1:
            raise RespNotOkException(502, "bad gateway")
        return None

    engine._run_planner_request = fake_request  # type: ignore[method-assign]
    engine._wait_for_recovery_backoff = AsyncMock(return_value=False)  # type: ignore[method-assign]

    await engine._run_planner_request_with_recovery(
        trigger_message=None, source_messages=[], round_index=0, round_text="", state=_state(),
    )

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_recovery_does_not_retry_permanent_error() -> None:
    engine = _build_engine()
    calls: list[int] = []

    async def fake_request(**kwargs):
        del kwargs
        calls.append(1)
        raise RespNotOkException(401, "unauthorized")

    engine._run_planner_request = fake_request  # type: ignore[method-assign]
    engine._wait_for_recovery_backoff = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with pytest.raises(RespNotOkException):
        await engine._run_planner_request_with_recovery(
            trigger_message=None, source_messages=[], round_index=0, round_text="", state=_state(),
        )

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_consumer_survives_prepare_and_turn_errors(monkeypatch) -> None:
    from src.maisaka import reasoning_engine

    queue = asyncio.Queue()
    for key in ("prepare_error", "turn_error", "success"):
        queue.put_nowait(key)
    runtime = SimpleNamespace(
        _running=True, _internal_turn_queue=queue, session_id="offline",
        chat_stream=SimpleNamespace(is_group_session=False), log_prefix="[test]",
        _agent_state="stop", _STATE_RUNNING="running",
        _update_stage_status=lambda *_args, **_kwargs: None,
    )
    engine = MaisakaReasoningEngine(runtime)
    monkeypatch.setattr(reasoning_engine.focus_mode_manager, "can_decide", lambda *_a, **_k: True)
    processed = []

    async def prepare(key):
        processed.append(key)
        if key == "prepare_error":
            raise ValueError("synthetic prepare failure")
        return SimpleNamespace(trigger_message=key, cached_messages=[], silent_reply_frequency=False)

    async def active(context):
        if context.trigger_message == "turn_error":
            raise RespNotOkException(502)
        runtime._running = False

    engine._prepare_turn_start_context = prepare
    engine._run_active_turn = active
    await asyncio.wait_for(engine.run_loop(), timeout=1)
    assert processed == ["prepare_error", "turn_error", "success"]


@pytest.mark.asyncio
async def test_actual_backoff_yields_and_stops_without_waiting() -> None:
    engine = _build_engine(pending_messages=True)
    assert await engine._wait_for_recovery_backoff(15) is True
    engine._runtime._running = False
    with pytest.raises(asyncio.CancelledError):
        await engine._wait_for_recovery_backoff(15)


@pytest.mark.asyncio
async def test_recovery_exhausts_after_two_retries() -> None:
    engine = _build_engine()
    calls: list[int] = []

    async def fake_request(**kwargs):
        del kwargs
        calls.append(1)
        raise RespNotOkException(502, "bad gateway")

    engine._run_planner_request = fake_request  # type: ignore[method-assign]
    engine._wait_for_recovery_backoff = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with pytest.raises(RespNotOkException):
        await engine._run_planner_request_with_recovery(
            trigger_message=None, source_messages=[], round_index=0, round_text="", state=_state(),
        )

    # 1 次原始请求 + 2 次恢复重试。
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_recovery_yields_to_new_message() -> None:
    engine = _build_engine(pending_messages=True)
    calls: list[int] = []

    async def fake_request(**kwargs):
        del kwargs
        calls.append(1)
        raise RespNotOkException(502, "bad gateway")

    engine._run_planner_request = fake_request  # type: ignore[method-assign]
    engine._wait_for_recovery_backoff = AsyncMock(return_value=True)  # type: ignore[method-assign]

    with pytest.raises(ReqAbortException):
        await engine._run_planner_request_with_recovery(
            trigger_message=None, source_messages=[], round_index=0, round_text="", state=_state(),
        )

    assert len(calls) == 1
