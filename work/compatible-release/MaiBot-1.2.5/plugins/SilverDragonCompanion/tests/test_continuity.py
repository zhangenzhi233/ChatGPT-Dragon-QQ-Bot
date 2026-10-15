"""带来源的事项状态机、重复控制及发送回执的离线验收。"""

from datetime import datetime, timedelta
import asyncio
import json
import logging

import pytest

from helpers import MAIN_QQ, STREAM_ID, MockTransport, build_message, make_plugin
from SilverDragonCompanion.context import ChatSnapshot
from SilverDragonCompanion.continuity import apply_updates, expire_items, gate_decision
from SilverDragonCompanion.policy import BEIJING_TZ
from SilverDragonCompanion.prompts import SchedulerDecision, parse_decision
from SilverDragonCompanion.scheduler import CompanionScheduler
from SilverDragonCompanion.state import AttemptRecord, CompanionState, StateStore

NOW = datetime(2026, 10, 15, 12, tzinfo=BEIJING_TZ)
SOURCE_TIME = NOW - timedelta(hours=5)
SOURCE = {"message_id": "u1", "role": "user", "time": SOURCE_TIME.isoformat(), "text": "今天机器人的程序还没有调试成功"}
ADD = {"operation": "add", "kind": "user_issue", "title": "机器人程序调试", "source_message_id": "u1",
       "source_quote": "机器人的程序还没有调试成功", "followup_after_minutes": 240, "expires_after_hours": 72}


def new_state():
    state = CompanionState(main_qq=MAIN_QQ)
    apply_updates(state.followups, [dict(ADD)], [dict(SOURCE)], NOW)
    return state


def test_add_requires_exact_quote_and_known_source():
    state = CompanionState(main_qq=MAIN_QQ)
    apply_updates(state.followups, [{**ADD, "source_quote": "用户明天考试"}, {**ADD, "source_message_id": "invented"}], [SOURCE], NOW)
    assert state.followups == {}


def test_repeated_review_does_not_duplicate_or_extend_expiry():
    state = new_state()
    original = dict(next(iter(state.followups.values())))
    apply_updates(state.followups, [ADD, {**ADD, "source_quote": "今天机器人的程序"}], [SOURCE], NOW + timedelta(hours=1))
    assert len(state.followups) == 1
    assert next(iter(state.followups.values())) == original


@pytest.mark.parametrize("role", ["bot", "user"])
def test_resolution_needs_later_user_evidence(role):
    state = new_state()
    key = next(iter(state.followups))
    result = {"message_id": "u2", "role": role, "time": NOW.isoformat(), "text": "修好了"}
    apply_updates(state.followups, [{"operation": "resolve", "item_id": key, "source_message_id": "u2", "source_quote": "修好了"}], [result], NOW)
    assert state.followups[key]["status"] == ("resolved" if role == "user" else "pending")


def test_expiry_is_not_completion_and_cannot_be_reopened():
    state = new_state()
    key = next(iter(state.followups))
    expire_items(state.followups, NOW + timedelta(days=4))
    assert state.followups[key]["status"] == "expired"
    apply_updates(state.followups, [ADD], [SOURCE], NOW + timedelta(days=4))
    assert len(state.followups) == 1 and state.followups[key]["status"] == "expired"


def test_bot_promise_source_must_be_actual_bot_message():
    state = CompanionState(main_qq=MAIN_QQ)
    apply_updates(state.followups, [{**ADD, "kind": "bot_promise"}], [SOURCE], NOW)
    assert not state.followups
    apply_updates(state.followups, [{**ADD, "kind": "bot_promise"}], [{**SOURCE, "role": "bot"}], NOW)
    assert len(state.followups) == 1


def test_pending_limit_and_short_or_old_sources_ignored():
    state = CompanionState(main_qq=MAIN_QQ)
    for i in range(12):
        source = {**SOURCE, "message_id": f"u{i}"}
        apply_updates(state.followups, [{**ADD, "source_message_id": f"u{i}"}], [source], NOW)
    assert len(state.followups) == 8
    fresh = CompanionState(main_qq=MAIN_QQ)
    apply_updates(fresh.followups, [ADD], [{**SOURCE, "time": (NOW - timedelta(days=8)).isoformat()}], NOW)
    assert fresh.followups == {}


def test_followup_gate_rejects_early_resolved_and_unknown():
    state = new_state()
    key = next(iter(state.followups))
    chat = ChatSnapshot(available=True, messages=[SOURCE], last_user_at=SOURCE["time"])
    decision = SchedulerDecision(True, topic="调试进展", basis_kind="followup", basis_id=key)
    assert gate_decision(decision, {"chat": chat}, state, NOW)[0]
    state.followups[key]["not_before"] = (NOW + timedelta(hours=1)).isoformat()
    assert not gate_decision(decision, {"chat": chat}, state, NOW)[0]
    decision.basis_kind, decision.basis_id = "chat", "u1"
    assert not gate_decision(decision, {"chat": chat}, state, NOW)[0]
    state.followups[key]["status"] = "resolved"
    assert not gate_decision(decision, {"chat": chat}, state, NOW)[0]
    decision.basis_id = "invented"
    assert not gate_decision(decision, {"chat": chat}, state, NOW)[0]


def test_unknown_attempt_blocks_same_followup_without_new_feedback():
    state = new_state()
    key = next(iter(state.followups))
    state.followups[key]["expires_at"] = (NOW + timedelta(days=6)).isoformat()
    state.attempts["a"] = AttemptRecord("a", NOW.isoformat(), STREAM_ID, "调试", "r", status="unknown", followup_id=key)
    decision = SchedulerDecision(True, topic="换个说法问进度", basis_kind="followup", basis_id=key)
    chat = ChatSnapshot(available=True, messages=[SOURCE], last_user_at=SOURCE["time"])
    assert not gate_decision(decision, {"chat": chat}, state, NOW + timedelta(days=4))[0]


def test_natural_contacts_limited_even_with_different_wording():
    state = CompanionState(main_qq=MAIN_QQ)
    state.attempts["a"] = AttemptRecord("a", (NOW - timedelta(hours=2)).isoformat(), STREAM_ID, "想你", "r", status="unknown", basis_kind="natural")
    assert not gate_decision(SchedulerDecision(True, topic="下午好", basis_kind="natural"), {"chat": ChatSnapshot()}, state, NOW)[0]


def test_v1_state_migration_preserves_dedup_and_frequency(tmp_path):
    store = StateStore(tmp_path, logging.getLogger("test"))
    state = CompanionState(main_qq=MAIN_QQ, trigger_count_today=2, trigger_day="2026-10-15")
    state.attempts["a"] = AttemptRecord("a", NOW.isoformat(), STREAM_ID, "旧话题", "r", status="unknown")
    store.save(state)
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw["schema_version"] = 1
    raw.pop("followups")
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    loaded, ok = store.load(MAIN_QQ)
    assert ok and loaded.schema_version == 2 and loaded.trigger_count_today == 2
    assert loaded.attempts["a"].status == "unknown" and loaded.followups == {}


def test_restart_preserves_followups_and_corrupt_new_state_fails_closed(tmp_path):
    store = StateStore(tmp_path, logging.getLogger("test"))
    store.save(new_state())
    loaded, ok = StateStore(tmp_path, logging.getLogger("test")).load(MAIN_QQ)
    assert ok and loaded.followups == new_state().followups
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    next(iter(raw["followups"].values()))["expires_at"] = "bad"
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    assert store.load(MAIN_QQ) == (None, False)


@pytest.mark.parametrize("status,segments", [("delivered", [{"status": "delivered"}]), ("partial", [{"status": "delivered"}, {"status": "unknown"}]), ("unknown", [])])
def test_host_receipt_updates_delivery_but_does_not_complete_item(tmp_path, status, segments):
    transport = MockTransport()
    plugin, ctx = make_plugin(transport, tmp_path)
    state = new_state()
    key = next(iter(state.followups))
    state.attempts["a"] = AttemptRecord("a", NOW.isoformat(), STREAM_ID, "调试", "r", status="queued", task_id="t1", delivery_status="queued", followup_id=key)
    transport.receipt = {"task_id": "t1", "stream_id": STREAM_ID, "status": status, "segments": segments, "updated_at": NOW.isoformat()}
    asyncio.run(CompanionScheduler(plugin, logging.getLogger("test"))._sync_receipts(state, StateStore(ctx.paths.data_dir, logging.getLogger("test")), NOW))
    assert state.attempts["a"].delivery_status == status
    assert state.followups[key]["status"] == "pending"
    assert transport.proactive_calls() == []
    assert not any(c[0] == "llm.generate" for c in transport.calls)


def test_inconsistent_or_wrong_scope_receipt_never_counts_as_delivered(tmp_path):
    transport = MockTransport()
    plugin, ctx = make_plugin(transport, tmp_path)
    state = CompanionState(main_qq=MAIN_QQ)
    state.attempts["a"] = AttemptRecord("a", NOW.isoformat(), STREAM_ID, "i", "r", status="queued", task_id="t1", delivery_status="queued")
    for stream, segments in [("other", [{"status": "delivered"}]), (STREAM_ID, [])]:
        transport.receipt = {"task_id": "t1", "stream_id": stream, "status": "delivered", "segments": segments}
        state.last_receipt_check_at = None
        asyncio.run(CompanionScheduler(plugin, logging.getLogger("test"))._sync_receipts(state, StateStore(ctx.paths.data_dir, logging.getLogger("test")), NOW))
        assert state.attempts["a"].delivery_status == "queued"


def test_scheduler_updates_items_during_silence_without_extra_model_call(tmp_path, monkeypatch):
    transport = MockTransport()
    transport.messages = [build_message(text=SOURCE["text"], from_user=True, ts=SOURCE_TIME.timestamp(), message_id="u1")]
    transport.llm_response["response"] = json.dumps({"should_chat": False, "next_check_minutes": 120, "followup_updates": [ADD]})
    plugin, ctx = make_plugin(transport, tmp_path)
    monkeypatch.setattr("SilverDragonCompanion.scheduler.beijing_now", lambda: NOW)
    store = StateStore(ctx.paths.data_dir, logging.getLogger("test"))
    state = CompanionState(main_qq=MAIN_QQ)
    asyncio.run(CompanionScheduler(plugin, logging.getLogger("test"))._evaluate(startup=None, state=state, now=NOW, check_key="scheduled:test", source="scheduled"))
    loaded, ok = store.load(MAIN_QQ)
    assert ok and len(loaded.followups) == 1
    assert len([c for c in transport.calls if c[0] == "llm.generate"]) == 1
    assert transport.proactive_calls() == []


def test_missing_basis_is_silent():
    assert not parse_decision('{"should_chat":true,"topic":"问候","next_check_minutes":60}', min_minutes=15, max_minutes=360).should_chat
