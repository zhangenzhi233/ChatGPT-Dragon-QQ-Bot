"""启动请求信号：消费去重、过期忽略、非法忽略、插件不伪造。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncio
import json
import logging

from helpers import MockTransport, make_plugin

from SilverDragonCompanion.startup import StartupSignalStore


def _store(tmp_path, ttl: float = 300.0) -> StartupSignalStore:
    return StartupSignalStore(tmp_path, logging.getLogger("t"), ttl_seconds=ttl)


def _write(tmp_path, request_id: str, requested_at: str) -> None:
    (tmp_path / "startup-request.json").write_text(
        json.dumps({"request_id": request_id, "requested_at": requested_at, "source": "start-qq-bot"}),
        encoding="utf-8",
    )


def test_consume_dedups_same_signal(tmp_path):
    store = _store(tmp_path)
    _write(tmp_path, "g1", datetime.now(timezone.utc).isoformat())
    first = store.consume()
    assert first is not None and first.request_id == "g1"
    # 文件已原子改名，再次消费返回 None，不会重复评估。
    assert store.consume() is None


def test_expired_request_ignored(tmp_path):
    store = _store(tmp_path, ttl=300.0)
    expired = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    _write(tmp_path, "g2", expired)
    assert store.consume() is None


def test_invalid_request_ignored_and_consumed(tmp_path):
    store = _store(tmp_path)
    _write(tmp_path, "", "")
    assert store.consume() is None
    assert store.consume() is None


def test_missing_request_returns_none(tmp_path):
    assert _store(tmp_path).consume() is None


def test_on_load_and_hot_reload_do_not_fabricate_signal(tmp_path):
    transport = MockTransport()
    plugin, ctx = make_plugin(transport, tmp_path, enabled=True)

    async def scenario():
        await plugin.on_load()
        assert not (ctx.paths.runtime_dir / "startup-request.json").exists()
        # 模拟热重载：配置更新不应伪造启动信号
        await plugin.on_config_update("self", plugin.get_plugin_config_data(), "1")
        assert not (ctx.paths.runtime_dir / "startup-request.json").exists()
        await plugin.on_unload()

    asyncio.run(scenario())
