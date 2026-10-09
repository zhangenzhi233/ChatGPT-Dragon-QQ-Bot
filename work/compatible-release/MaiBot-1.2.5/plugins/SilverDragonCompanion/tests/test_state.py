"""持久状态：原子读写、损坏检测、主号切换与去重裁剪。"""

from __future__ import annotations

from pathlib import Path

import logging

from SilverDragonCompanion.state import AttemptRecord, CompanionState, StateStore


def _store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path, logging.getLogger("test"))


def test_missing_file_returns_fresh_state(tmp_path):
    state, ok = _store(tmp_path).load("123")
    assert ok is True
    assert state is not None
    assert state.main_qq == "123"
    assert state.next_check_at is None


def test_save_and_load_roundtrip(tmp_path):
    store = _store(tmp_path)
    state = CompanionState(main_qq="123", next_check_at="2026-10-08T09:00:00+08:00")
    state.attempts["a"] = AttemptRecord(attempt_id="a", decided_at="2026-10-08T09:00:00+08:00", stream_id="s", intent="i", reason="r", status="queued")
    store.save(state)
    loaded, ok = store.load("123")
    assert ok is True
    assert loaded.next_check_at == state.next_check_at
    assert loaded.attempts["a"].status == "queued"


def test_corrupt_json_returns_not_ok(tmp_path):
    store = _store(tmp_path)
    store.path.write_text("{not json", encoding="utf-8")
    state, ok = store.load("123")
    assert ok is False
    assert state is None


def test_wrong_schema_returns_not_ok(tmp_path):
    store = _store(tmp_path)
    store.path.write_text('{"schema_version": 99, "main_qq": "123"}', encoding="utf-8")
    _state, ok = store.load("123")
    assert ok is False


def test_bad_attempt_status_returns_not_ok(tmp_path):
    store = _store(tmp_path)
    store.path.write_text(
        '{"schema_version": 1, "main_qq": "123", "trigger_count_today": 0, '
        '"attempts": {"a": {"attempt_id": "a", "status": "not-a-status"}}}',
        encoding="utf-8",
    )
    _state, ok = store.load("123")
    assert ok is False


def test_main_qq_change_resets_to_fresh(tmp_path):
    store = _store(tmp_path)
    state = CompanionState(main_qq="old", next_check_at="2026-10-08T09:00:00+08:00")
    state.attempts["a"] = AttemptRecord(attempt_id="a", decided_at="2026-10-08T09:00:00+08:00", stream_id="s", intent="i", reason="r", status="queued")
    store.save(state)
    loaded, ok = store.load("new")
    assert ok is True
    assert loaded.main_qq == "new"
    assert loaded.attempts == {}


def test_attempts_trimmed_to_max(tmp_path):
    store = _store(tmp_path)
    state = CompanionState(main_qq="123")
    for index in range(150):
        state.attempts[f"a{index}"] = AttemptRecord(
            attempt_id=f"a{index}", decided_at="2026-10-08T09:00:00+08:00", stream_id="s", intent="i", reason="r", status="queued"
        )
    store.save(state)
    loaded, ok = store.load("123")
    assert ok is True
    assert len(loaded.attempts) <= 100
