"""离线验证配图选择：从正文提取短标签、校验非空、受控通用回退；不调用模型/QQ。"""

from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import base64
import json
from io import BytesIO
from PIL import Image
import importlib
import sys
import unittest


PACKAGE = "local_maizone_image_test"
module = ModuleType(PACKAGE)
module.__path__ = [str(Path(__file__).resolve().parents[1])]
sys.modules[PACKAGE] = module
image_module = importlib.import_module(PACKAGE + ".image")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _valid_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2)).save(output, format="PNG")
    return output.getvalue()


class ImageSelectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.get_by_description = AsyncMock()
        self.ctx = SimpleNamespace(
            emoji=SimpleNamespace(get_by_description=self.get_by_description),
            config=SimpleNamespace(get=AsyncMock(return_value={"nickname": "银白龙"})),
        )
        image_module.plugin_context = SimpleNamespace(ctx=self.ctx)

    async def test_extracts_emotion_tag_instead_of_whole_body(self):
        self.get_by_description.return_value = {"base64": _b64(_valid_image())}
        result = await image_module.generate_emoji_image("今天真开心，分享一下日常。")
        self.assertIsNotNone(result)
        called_descriptions = [call.kwargs["description"] for call in self.get_by_description.await_args_list]
        self.assertTrue(called_descriptions)
        self.assertEqual(called_descriptions[0], "银白龙 开心")
        self.assertTrue(all(d.startswith("银白龙 ") for d in called_descriptions))
        self.assertNotEqual(called_descriptions[0], "今天真开心，分享一下日常。")

    async def test_rejects_empty_base64_and_tries_next_candidate(self):
        responses = {"银白龙 开心": {"base64": ""}, "银白龙 问候": {"base64": _b64(_valid_image())}}
        self.get_by_description.side_effect = lambda description: responses.get(description)
        result = await image_module.generate_emoji_image("今天真开心")
        self.assertIsNotNone(result)

    async def test_no_match_returns_none_explicitly(self):
        self.get_by_description.return_value = None
        result = await image_module.generate_emoji_image("今天真开心")
        self.assertIsNone(result)

    async def test_generic_character_tag_fallback(self):
        self.get_by_description.side_effect = (
            lambda description: {"base64": _b64(_valid_image())} if description == "银白龙 问候" else None
        )
        result = await image_module.generate_emoji_image("随便写点什么。")
        self.assertIsNotNone(result)
        called = [call.kwargs["description"] for call in self.get_by_description.await_args_list]
        self.assertIn("银白龙 问候", called)

    def test_generic_tag_exists_in_shipped_character_catalog(self):
        from src.emoji_system import emoji_identity as identity
        assets = Path(__file__).resolve().parents[6] / "assets/stickers"
        stickers = {}
        for path in assets.glob("*/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            for item in manifest["stickers"]:
                stickers[item["sha256"]] = identity.CharacterEmoji(
                    manifest["character"]["name"], item["name"], item["visual_description"], tuple(item["tags"])
                )
        self.assertTrue(stickers)
        catalog = identity._Catalog({"chatgpt": "ChatGPT"}, stickers)
        pool = [(key, sticker.tags) for key, sticker in catalog.stickers.items()]
        with patch.object(identity, "_load_catalog", return_value=catalog):
            for tag in image_module._CHARACTER_GENERIC_TAGS:
                self.assertTrue(identity.score_emoji_candidates(f"ChatGPT {tag}", pool, current_character_name="ChatGPT"))

    async def test_corrupt_image_is_rejected(self):
        self.get_by_description.return_value = {"base64": _b64(b"img")}
        self.assertIsNone(await image_module.generate_emoji_image("开心"))

    async def test_missing_character_does_not_query_unscoped_images(self):
        self.ctx.config.get.return_value = {}
        self.assertIsNone(await image_module.generate_emoji_image("开心"))
        self.get_by_description.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
