# -*- coding: utf-8 -*-
import hashlib
import json
import unittest
from pathlib import Path

from PIL import Image, ImageChops

from src.jb_quickpanel.features import registry


ROOT = Path(__file__).resolve().parents[1]


class TableThumbnailAssetTests(unittest.TestCase):
    def test_all_current_table_tools_have_unique_consistent_thumbnails(self):
        config = json.loads((ROOT / "config/config.json").read_text(encoding="utf-8"))
        tools = registry.with_current_table_tools(config["table_tools"])

        self.assertEqual(len(tools), 20)
        thumb_paths = [ROOT / item["thumb"] for item in tools]
        self.assertEqual(len(set(thumb_paths)), 20)

        hashes = set()
        for item, path in zip(tools, thumb_paths):
            with self.subTest(action_id=item["action_id"]):
                self.assertTrue(path.is_file(), path)
                hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
                with Image.open(path) as image:
                    self.assertEqual(image.mode, "RGBA")
                    self.assertEqual(image.size, (512, 512))
                    self.assertIsNotNone(image.getchannel("A").getbbox())

        self.assertEqual(len(hashes), 20)

    def test_trimmed_preview_keeps_all_icon_artwork(self):
        config = json.loads((ROOT / "config/config.json").read_text(encoding="utf-8"))
        for tool in registry.with_current_table_tools(config["table_tools"]):
            with self.subTest(action_id=tool["action_id"]):
                with Image.open(ROOT / tool["thumb"]) as image:
                    white = Image.new("RGBA", image.size, "white")
                    visible = Image.alpha_composite(white, image.convert("RGBA")).convert("RGB")
                    bounds = ImageChops.difference(visible, white.convert("RGB")).getbbox()
                self.assertIsNotNone(bounds)
                left, top, right, bottom = bounds
                self.assertGreaterEqual(left, 72)
                self.assertGreaterEqual(top, 52)
                self.assertLessEqual(right, 440)
                self.assertLessEqual(bottom, 356)


if __name__ == "__main__":
    unittest.main()
