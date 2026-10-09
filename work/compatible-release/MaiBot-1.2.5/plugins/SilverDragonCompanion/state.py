"""银白龙主动聊天持久状态。

状态按用户（主号）持久化在插件 data_dir，原子写入；重启后保留下次评估时间与
尝试去重记录。状态文件损坏时拒绝主动发送（返回 ``ok=False``），而不是重置去重再发。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import json
import os

SCHEMA_VERSION = 1
STATE_FILENAME = "companion-state.json"
# 去重表最多保留的尝试记录数，防止状态文件无限膨胀。
MAX_ATTEMPTS = 100
# 尝试状态：pending=已落盘尚未入队；queued=已入队（不等于已发送）；failed=入队失败；
# skipped=入队前判定过期/被打断；unknown=结果不明（不自动补发）。
VALID_ATTEMPT_STATUSES = {"pending", "queued", "failed", "skipped", "unknown"}


@dataclass
class AttemptRecord:
    """一次主动触发的去重记录。"""

    attempt_id: str
    decided_at: str
    stream_id: str
    intent: str
    reason: str
    status: str = "pending"


@dataclass
class CompanionState:
    """单个主号的调度持久状态。"""

    schema_version: int = SCHEMA_VERSION
    main_qq: str = ""
    next_check_at: str | None = None
    last_evaluation_at: str | None = None
    last_trigger_at: str | None = None
    last_startup_at: str | None = None
    trigger_day: str = ""
    trigger_count_today: int = 0
    attempts: dict[str, AttemptRecord] = field(default_factory=dict)


class StateStore:
    """负责状态文件的原子读写与损坏检测。"""

    def __init__(self, data_dir: Path, logger: Any) -> None:
        self._path = Path(data_dir) / STATE_FILENAME
        self._logger = logger

    @property
    def path(self) -> Path:
        return self._path

    def load(self, main_qq: str) -> tuple[CompanionState | None, bool]:
        """读取状态。

        Returns:
            (state, ok)：文件缺失时返回该主号的空状态且 ok=True；文件损坏或 schema
            不合法时返回 (None, False)，调用方应拒绝主动发送。
        """
        if not self._path.exists():
            return CompanionState(main_qq=main_qq), True
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            self._logger.error(f"主动聊天状态文件无法解析：{type(exc).__name__}；拒绝主动发送")
            return None, False

        state = self._from_dict(raw)
        if state is None:
            self._logger.error("主动聊天状态文件结构非法；拒绝主动发送")
            return None, False
        if state.main_qq != main_qq:
            # 主号变更属于显式配置变化，返回新主号的空状态，不算损坏。
            return CompanionState(main_qq=main_qq), True
        return state, True

    def save(self, state: CompanionState) -> None:
        """原子写入状态（临时文件 + 替换）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".json.tmp")
        payload = self._to_dict(state)
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, self._path)

    def _to_dict(self, state: CompanionState) -> dict[str, Any]:
        attempts = state.attempts
        if len(attempts) > MAX_ATTEMPTS:
            # 按插入顺序裁剪最旧记录，仅保留最近 MAX_ATTEMPTS 条。
            trimmed = dict(list(attempts.items())[-MAX_ATTEMPTS:])
        else:
            trimmed = attempts
        return {
            "schema_version": state.schema_version,
            "main_qq": state.main_qq,
            "next_check_at": state.next_check_at,
            "last_evaluation_at": state.last_evaluation_at,
            "last_trigger_at": state.last_trigger_at,
            "last_startup_at": state.last_startup_at,
            "trigger_day": state.trigger_day,
            "trigger_count_today": state.trigger_count_today,
            "attempts": {key: asdict(record) for key, record in trimmed.items()},
        }

    @staticmethod
    def _from_dict(raw: Any) -> CompanionState | None:
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            return None
        main_qq = raw.get("main_qq")
        if not isinstance(main_qq, str):
            return None
        for name in ("next_check_at", "last_evaluation_at", "last_trigger_at", "last_startup_at"):
            stamp = raw.get(name)
            if stamp is not None:
                if not isinstance(stamp, str):
                    return None
                try:
                    parsed = datetime.fromisoformat(stamp)
                except ValueError:
                    return None
                if parsed.tzinfo is None:
                    return None
        day = raw.get("trigger_day", "")
        if not isinstance(day, str):
            return None
        if day:
            try:
                datetime.strptime(day, "%Y-%m-%d")
            except ValueError:
                return None
        attempts_raw = raw.get("attempts", {})
        if not isinstance(attempts_raw, dict):
            return None
        attempts: dict[str, AttemptRecord] = {}
        for key, value in attempts_raw.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                return None
            status = value.get("status")
            if status not in VALID_ATTEMPT_STATUSES:
                return None
            record = AttemptRecord(
                attempt_id=str(value.get("attempt_id") or ""),
                decided_at=str(value.get("decided_at") or ""),
                stream_id=str(value.get("stream_id") or ""),
                intent=str(value.get("intent") or ""),
                reason=str(value.get("reason") or ""),
                status=str(status),
            )
            if not record.attempt_id:
                return None
            try:
                decided = datetime.fromisoformat(record.decided_at)
            except ValueError:
                return None
            if decided.tzinfo is None or record.attempt_id != key:
                return None
            attempts[key] = record
        trigger_count = raw.get("trigger_count_today")
        if type(trigger_count) is not int or trigger_count < 0:
            return None
        state = CompanionState(
            schema_version=SCHEMA_VERSION,
            main_qq=main_qq,
            next_check_at=_as_optional_str(raw.get("next_check_at")),
            last_evaluation_at=_as_optional_str(raw.get("last_evaluation_at")),
            last_trigger_at=_as_optional_str(raw.get("last_trigger_at")),
            last_startup_at=_as_optional_str(raw.get("last_startup_at")),
            trigger_day=str(raw.get("trigger_day") or ""),
            trigger_count_today=trigger_count,
            attempts=attempts,
        )
        return state


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    return None


def utc_now_iso() -> str:
    """当前时间 ISO（带时区），用于持久化字段。"""
    return datetime.now().astimezone().isoformat()
