"""离线验证定时说说「准备/发布」边界与有限重排；不调用模型或 QQ。"""

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


class ScheduleBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "schedule_state.json"
        self.senders = []
        self.prepare = AsyncMock(return_value=(True, SimpleNamespace(message="synthetic", images_list=[b"img"], qzone=None)))
        self.publish = AsyncMock(return_value=(True, "synthetic publication"))
        self.prepare_patcher = patch.object(tasks, "prepare_feed", self.prepare)
        self.publish_patcher = patch.object(tasks, "publish_prepared_feed", self.publish)
        self.prepare_patcher.start()
        self.publish_patcher.start()

    def sender(self, schedule=None, fluctuation=0):
        config = SimpleNamespace(schedule=schedule or ["20:00"], fluctuation=fluctuation,
                                 daily_probability=1.0, random_topic=True, fixed_topic=["synthetic"])
        sender = tasks.ScheduleSender(SimpleNamespace(config=SimpleNamespace(auto_send=config)))
        sender.state_path = self.path
        sender.last_reset_date = datetime.now().date()
        self.senders.append(sender)
        return sender

    async def asyncTearDown(self):
        for sender in self.senders:
            await sender.stop()
        self.prepare_patcher.stop()
        self.publish_patcher.stop()
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
        self.publish.assert_not_awaited()

    async def test_previous_day_does_not_suppress_new_day(self):
        self.path.write_text(json.dumps({"date": (datetime.now().date() - timedelta(days=1)).isoformat(),
                                         "times": [], "send_enabled": True, "attempted": True}), encoding="utf-8")
        sender = self.sender()
        await sender.start()
        self.assertFalse(sender.attempted_today)
        self.assertEqual(sender.fluctuate_table, ["20:00"])

    async def test_preparation_failure_reschedules_without_publishing(self):
        self.prepare.return_value = (False, "未找到可用配图，未发布")
        with patch.object(tasks, "PREP_RETRY_WINDOW_START", "00:00"), patch.object(tasks, "PREP_RETRY_WINDOW_END", "23:59"):
            sender = self.sender()
            sender.prep_retries = 0
            await sender._attempt_prepare_and_publish()
            self.publish.assert_not_awaited()
            self.assertFalse(sender.attempted_today)
            self.assertEqual(sender.prep_retries, 1)
            self.assertIsNotNone(sender.prep_next_at)

    async def test_out_of_window_does_not_reschedule(self):
        self.prepare.return_value = (False, "未找到可用配图，未发布")
        with patch.object(tasks, "PREP_RETRY_WINDOW_START", "00:00"), patch.object(tasks, "PREP_RETRY_WINDOW_END", "00:01"):
            sender = self.sender()
            sender.prep_retries = 0
            await sender._attempt_prepare_and_publish()
            self.publish.assert_not_awaited()
            self.assertEqual(sender.prep_retries, 0)
            self.assertIsNone(sender.prep_next_at)

    async def test_prep_retry_survives_restart_with_cap(self):
        with patch.object(tasks, "PREP_RETRY_WINDOW_START", "00:00"), patch.object(tasks, "PREP_RETRY_WINDOW_END", "23:59"):
            first = self.sender()
            first.last_reset_date = datetime.now().date()
            first.prep_retries = 1
            first.prep_next_at = "20:00"
            first.attempted_today = False
            first._save_state()
            await first.stop()
            second = self.sender()
            await second.start()
            self.assertEqual(second.prep_retries, 1)
            self.assertEqual(second.prep_next_at, "20:00")

    async def test_publish_failure_marks_attempted_and_does_not_resend(self):
        self.publish.return_value = (False, "说说发布失败")
        sender = self.sender()
        await sender._attempt_prepare_and_publish()
        self.publish.assert_awaited_once()
        self.assertTrue(sender.attempted_today)
        self.assertEqual(sender.prep_retries, 0)

    async def test_write_state_failure_does_not_publish(self):
        sender = self.sender()
        with patch.object(sender, "_save_state", return_value=False):
            await sender._attempt_prepare_and_publish()
        self.publish.assert_not_awaited()

    async def test_publish_exception_is_never_replayed(self):
        self.publish.side_effect = TimeoutError("ambiguous acknowledgement")
        sender = self.sender()
        with self.assertRaises(TimeoutError):
            await sender._attempt_prepare_and_publish()
        await sender._attempt_prepare_and_publish()
        self.publish.assert_awaited_once()

    async def test_prepare_exceptions_have_persistent_retry_cap(self):
        self.prepare.side_effect = TimeoutError("preparation only")
        class Evening(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 10, 19, 0)
        with patch.object(tasks.datetime, "datetime", Evening):
            sender = self.sender()
            for _ in range(3):
                await sender._attempt_prepare_and_publish()
            self.assertEqual(sender.prep_retries, 2)
            self.assertIsNone(sender.prep_next_at)
            self.publish.assert_not_awaited()
            restored = self.sender()
            restored._restore_today_state()
            self.assertEqual(restored.prep_retries, 2)

    async def test_invalid_state_refuses_automatic_publication(self):
        for payload in ([], {"date": datetime.now().date().isoformat(), "attempted": "false"}):
            self.path.write_text(json.dumps(payload), encoding="utf-8")
            sender = self.sender()
            sender._restore_today_state()
            await sender._attempt_prepare_and_publish()
            self.assertTrue(sender.attempted_today)
        self.publish.assert_not_awaited()

    async def test_retry_does_not_cross_22_hour_boundary(self):
        class LateEvening(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 10, 21, 50)
        sender = self.sender()
        with patch.object(tasks.datetime, "datetime", LateEvening):
            sender._schedule_prep_retry()
        self.assertIsNone(sender.prep_next_at)
        self.assertEqual(sender.prep_retries, 0)


if __name__ == "__main__":
    unittest.main()
