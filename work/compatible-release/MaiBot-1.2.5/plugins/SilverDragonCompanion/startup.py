"""银白龙主动聊天启动请求信号。

一键启动脚本在健康检查成功后原子写入 startup-request.json（GUID + requested_at）。
插件只轮询并消费该文件，绝不在加载 / 热重载时自行伪造启动信号；CheckOnly 也不会写。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json
import os

from .policy import parse_iso, utc_now


@dataclass
class StartupRequest:
    """一次合法启动请求。"""

    request_id: str
    requested_at: str


class StartupSignalStore:
    """读取 / 原子消费启动请求文件，带过期与消费去重。"""

    def __init__(self, runtime_dir: Path, logger: Any, ttl_seconds: float = 300.0) -> None:
        self._path = Path(runtime_dir) / "startup-request.json"
        self._consumed_path = Path(runtime_dir) / "startup-request.consumed.json"
        self._logger = logger
        self._ttl_seconds = ttl_seconds

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> dict[str, Any] | None:
        """读取请求文件内容（不消费）。"""
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            return None
        return raw if isinstance(raw, dict) else None

    def consume(self) -> StartupRequest | None:
        """读取并原子消费一个合法且未过期的启动请求；非法/过期请求也标记已消费。"""
        raw = self.read()
        if raw is None:
            return None
        if not self._mark_consumed(raw):
            return None
        request_id = str(raw.get("request_id") or "").strip()
        requested_at = str(raw.get("requested_at") or "").strip()
        if not request_id or not requested_at:
            self._logger.warning("启动请求缺少 request_id 或 requested_at，已忽略")
            return None
        parsed_at = parse_iso(requested_at)
        if parsed_at is None:
            self._logger.warning("启动请求 requested_at 无法解析，已忽略")
            return None
        age = (utc_now() - parsed_at).total_seconds()
        if age < -30 or age > self._ttl_seconds:
            self._logger.info("启动请求已过期，忽略")
            return None
        return StartupRequest(request_id=request_id, requested_at=requested_at)

    def _mark_consumed(self, raw: dict[str, Any]) -> bool:
        """原子地把请求文件改名为已消费标记；重复消费只保留最后一次请求 ID。"""
        try:
            os.replace(self._path, self._consumed_path)
        except OSError as exc:
            self._logger.warning(f"启动请求消费改名失败：{type(exc).__name__}")
            return False
        # 便于排障：保留已消费文件，内容仅含非敏感字段。
        try:
            safe = {
                "request_id": str(raw.get("request_id") or ""),
                "requested_at": str(raw.get("requested_at") or ""),
                "consumed_at": utc_now().isoformat(),
            }
            self._consumed_path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
        return True
