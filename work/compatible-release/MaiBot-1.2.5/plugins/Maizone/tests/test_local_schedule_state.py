"""离线验证随机计划持久化与发送异常后不重试；不调用模型或 QQ。"""

from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import asyncio
import importlib
import json
import sys
import tempfile
import unittest


PACKAGE = "local_maizone_schedule_test"
module = ModuleType(PACKAGE)
module.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = module
tasks = importlib.import_module(PACKAGE + ".tasks")


class SchedulePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "schedule_state.json"
        self.senders = []
        self.network = AsyncMock(return_value=(True, "synthetic"))
        self.patcher = patch.object(tasks, "send_feed", self.network)
        self.patcher.start()

    def sender(self, schedule=None, fluctuation=0):
        config = SimpleNamespace(schedule=schedule or ["20:00"], fluctuation=fluctuation,
                                 daily_probability=1.0, random_topic=True, fixed_topic=["synthetic"])
        sender = tasks.ScheduleSender(SimpleNamespace(config=SimpleNamespace(auto_send=config)))
        sender.state_path = self.path
        self.senders.append(sender)
        return sender

    async def asyncTearDown(self):
        for sender in self.senders:
            await sender.stop()
        self.patcher.stop()
        self.directory.cleanup()

    async def test_random_plan_survives_restart(self):
        first = self.sender(fluctuation=120)
        await first.start()
        saved = first.fluctuate_table.copy()
        await first.stop()
        second = self.sender(fluctuation=120)
        await second.start()
        self.assertEqual(second.fluctuate_table, saved)

    async def test_claimed_day_survives_restart_without_republishing(self):
        first = self.sender()
        await first.start()
        first.mark_attempted_today()
        await first.stop()
        second = self.sender()
        await second.start()
        await asyncio.sleep(0)
        self.assertTrue(second.attempted_today)
        self.assertEqual(second.fluctuate_table, [])
        self.network.assert_not_awaited()

    async def test_previous_day_does_not_suppress_new_day(self):
        self.path.write_text(json.dumps({"date": (datetime.now().date() - timedelta(days=1)).isoformat(),
                                         "times": [], "send_enabled": True, "attempted": True}), encoding="utf-8")
        sender = self.sender()
        await sender.start()
        self.assertFalse(sender.attempted_today)
        self.assertEqual(sender.fluctuate_table, ["20:00"])

    async def test_publish_exception_is_claimed_and_not_retried_after_restart(self):
        self.network.side_effect = RuntimeError("synthetic request failure")
        first = self.sender([datetime.now().strftime("%H:%M")])
        await first.start()
        await asyncio.sleep(0)
        await first.stop()
        self.assertTrue(first.attempted_today)
        second = self.sender([datetime.now().strftime("%H:%M")])
        await second.start()
        await asyncio.sleep(0)
        self.assertEqual(self.network.await_count, 1)


if __name__ == "__main__":
    unittest.main()
