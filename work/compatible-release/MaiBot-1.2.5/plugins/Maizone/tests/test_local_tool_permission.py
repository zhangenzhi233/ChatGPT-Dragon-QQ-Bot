"""离线验证真实请求者权限，全部发送与模型请求都以 mock 替代。"""

from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import importlib
import sys
import unittest


PACKAGE = "local_maizone_permission_test"
module = ModuleType(PACKAGE)
module.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = module
plugin_module = importlib.import_module(PACKAGE + ".plugin")
utils = importlib.import_module(PACKAGE + ".utils")


class ToolPermissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.plugin = plugin_module.MaizonePlugin()
        config = self.plugin.get_default_config()
        config["authority"].update(send_authority_type="whitelist", send_whitelist=["12345678"],
                                  read_authority_type="whitelist", read_whitelist=["12345678"])
        self.plugin.set_plugin_config(config)
        self.db = AsyncMock(return_value=[])
        self.plugin._set_context(SimpleNamespace(db=SimpleNamespace(get=self.db)))
        self.publisher = AsyncMock(return_value=(True, "synthetic publication"))
        self.patcher = patch.object(plugin_module, "send_feed", self.publisher)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    async def test_owner_with_unrecognized_nickname_can_publish(self):
        result = await self.plugin.handle_send_feed_tool("synthetic", nickname="不存在的称呼", user_id="12345678", platform="qq")
        self.assertTrue(result[0])
        self.publisher.assert_awaited_once_with("synthetic")
        self.db.assert_not_awaited()

    async def test_owner_without_nickname_can_publish(self):
        result = await self.plugin.handle_send_feed_tool("synthetic", user_id=12345678, platform="qq")
        self.assertTrue(result[0])

    async def test_non_owner_cannot_gain_permission_by_spoofing_nickname(self):
        result = await self.plugin.handle_send_feed_tool("synthetic", nickname="主人", user_id="87654321", platform="qq")
        self.assertFalse(result[0])
        self.publisher.assert_not_awaited()

    async def test_missing_identity_is_denied(self):
        result = await self.plugin.handle_send_feed_tool("synthetic", nickname="主人")
        self.assertFalse(result[0])
        self.publisher.assert_not_awaited()

    async def test_non_qq_context_is_denied(self):
        result = await self.plugin.handle_send_feed_tool("synthetic", user_id="12345678", platform="other")
        self.assertFalse(result[0])
        self.publisher.assert_not_awaited()

    async def test_read_permission_uses_real_caller(self):
        self.db.return_value = [{"user_id": "87654321"}]
        reader = AsyncMock(return_value=(True, []))
        with patch.object(plugin_module, "read_feed", reader):
            result = await self.plugin.handle_read_feed_tool("未知称呼", "目标", user_id="12345678", platform="qq")
        self.assertTrue(result[0])
        reader.assert_awaited_once()

    async def test_status_query_is_read_only(self):
        qzone = SimpleNamespace(uin="99999999", get_list=AsyncMock(return_value=[
            {"created_time": "2026-10-04 10:00", "content": "synthetic", "images": []}]))
        with patch.object(plugin_module, "renew_cookies", AsyncMock()), patch.object(plugin_module, "create_qzone_api", return_value=qzone):
            result = await self.plugin.handle_get_my_feeds(user_id="12345678", platform="qq")
        self.assertTrue(result[0])
        self.publisher.assert_not_awaited()
        qzone.get_list.assert_awaited_once_with("99999999", 5, False)

    async def test_status_query_rejects_non_owner_without_space_request(self):
        with patch.object(plugin_module, "renew_cookies", AsyncMock()) as cookies:
            result = await self.plugin.handle_get_my_feeds(user_id="87654321", platform="qq")
        self.assertFalse(result[0])
        cookies.assert_not_awaited()

    async def test_summary_error_does_not_return_raw_chat(self):
        utils.set_utils_plugin_context(SimpleNamespace(ctx=SimpleNamespace(logger=SimpleNamespace(error=lambda *_: None),
                                                                            llm=SimpleNamespace(generate=AsyncMock(side_effect=RuntimeError("synthetic"))))))
        config = self.plugin.config.send
        config.chat_memory_mode = "summary"
        with patch.object(utils.MessageFetcher, "format_chat_messages", return_value="PRIVATE_CHAT_SENTINEL"):
            result = await utils._process_chat_messages_by_mode([{}], config)
        self.assertNotIn("PRIVATE_CHAT_SENTINEL", result)


if __name__ == "__main__":
    unittest.main()
