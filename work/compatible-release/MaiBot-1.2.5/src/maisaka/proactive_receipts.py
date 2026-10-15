"""主动任务的持久投递回执；不保存正文、不提供发送或重放功能。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
from uuid import uuid4


class ReceiptStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.run_id = uuid4().hex

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("tasks"), dict):
            raise ValueError("主动投递回执损坏")
        return raw["tasks"]

    def _save(self, tasks: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 同一宿主事件循环内同步读写；不宣称支持多进程并发。
        tasks = dict(list(tasks.items())[-256:])
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"schema_version": 1, "tasks": tasks}, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def queue(self, task_id: str, plugin_id: str, stream_id: str) -> None:
        tasks = self._load()
        if task_id in tasks:
            raise ValueError("主动任务编号重复")
        tasks[task_id] = {
            "task_id": task_id, "plugin_id": plugin_id, "stream_id": stream_id,
            "status": "queued", "segments": [], "updated_at": self._now(), "run_id": self.run_id,
        }
        self._save(tasks)

    def get(self, task_id: str, plugin_id: str, stream_id: str) -> dict[str, Any] | None:
        record = self._load().get(task_id)
        if not isinstance(record, dict) or record.get("plugin_id") != plugin_id or record.get("stream_id") != stream_id:
            return None
        # 副本，避免读接口改变持久状态。
        result = json.loads(json.dumps(record))
        if result["status"] in {"queued", "running"} and result.get("run_id") != self.run_id:
            result["status"] = "unknown"
        result.pop("run_id", None)
        return result

    def plan(self, task_id: str, stream_id: str, count: int, *, action: str = "reply") -> int:
        tasks = self._load()
        record = self._owned(tasks, task_id, stream_id)
        if action in record.get("actions", []) or any(s["status"] != "delivered" for s in record["segments"]):
            raise ValueError("该主动任务已进入过此发送动作或存在不明回执，不重放")
        offset = len(record["segments"])
        if count < 1 or offset + count > 1000:
            raise ValueError("主动回复分段数量非法")
        record["segments"].extend({"status": "planned"} for _ in range(count))
        record.setdefault("actions", []).append(action)
        record["status"] = "running"
        record["updated_at"] = self._now()
        self._save(tasks)
        return offset

    def segment(self, task_id: str, stream_id: str, index: int, *, sent: bool | None = None, message_id: str = "") -> None:
        tasks = self._load()
        record = self._owned(tasks, task_id, stream_id)
        segment = record["segments"][index]
        if segment["status"] == "delivered":
            return
        # 发送前必须先写 pending；回执不明不能算失败或已送达。
        segment["status"] = "delivered" if sent is True else "pending" if sent is None else "unknown"
        if sent is True and message_id:
            segment["message_id"] = message_id[:200]
        record["updated_at"] = self._now()
        self._save(tasks)

    def finish(self, task_id: str, stream_id: str, *, outcome: str = "finished") -> None:
        tasks = self._load()
        record = self._owned(tasks, task_id, stream_id)
        if record["status"] in {"delivered", "partial", "unknown", "no_reply", "failed", "superseded"}:
            return
        segments = record["segments"]
        delivered = sum(s["status"] == "delivered" for s in segments)
        uncertain = any(s["status"] in {"pending", "unknown"} for s in segments)
        if segments and delivered == len(segments):
            status = "delivered"
        elif delivered:
            status = "partial"
        elif uncertain:
            status = "unknown"
        elif outcome in {"failed", "superseded"}:
            status = outcome
        else:
            status = "no_reply"
        record.update(status=status, updated_at=self._now())
        self._save(tasks)

    @staticmethod
    def _owned(tasks: dict[str, Any], task_id: str, stream_id: str) -> dict[str, Any]:
        record = tasks.get(task_id)
        if not isinstance(record, dict) or record.get("stream_id") != stream_id:
            raise ValueError("主动任务回执归属不匹配")
        return record

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


receipts = ReceiptStore(Path(__file__).resolve().parents[2] / "data" / "proactive-receipts.json")


async def invoke_tracked_media(runtime: Any, registry: Any, invocation: Any, context: Any) -> Any:
    """为返回值代表平台发送结果的内置图片/表情工具关联同一任务。"""
    task_id = getattr(runtime, "_active_proactive_task_id", None)
    if not task_id or invocation.tool_name not in {"send_emoji", "send_image"}:
        return await registry.invoke(invocation, context)
    from src.core.tooling import ToolExecutionResult

    try:
        if runtime._has_pending_messages():
            finish_runtime_task(runtime, outcome="superseded")
            return ToolExecutionResult(tool_name=invocation.tool_name, success=False,
                                       error_message="新消息已到达，取消主动发送。", stop_after_execution=True)
        index = receipts.plan(task_id, runtime.session_id, 1, action=invocation.tool_name)
        receipts.segment(task_id, runtime.session_id, index)
    except (OSError, ValueError, KeyError, TypeError):
        return ToolExecutionResult(tool_name=invocation.tool_name, success=False,
                                   error_message="主动任务回执不可用或已经尝试过此动作，不重放。", stop_after_execution=True)
    result = await registry.invoke(invocation, context)
    receipts.segment(task_id, runtime.session_id, index, sent=result.success is True)
    return result


def finish_runtime_task(runtime: Any, *, outcome: str = "finished") -> None:
    task_id = getattr(runtime, "_active_proactive_task_id", None)
    if not task_id:
        return
    try:
        receipts.finish(task_id, runtime.session_id, outcome=outcome)
    except (OSError, ValueError, KeyError, TypeError):
        from src.common.logger import get_logger

        get_logger("maisaka.receipts").warning("主动任务最终回执不可用；保留不确定性，不补发")
    finally:
        runtime._active_proactive_task_id = None
