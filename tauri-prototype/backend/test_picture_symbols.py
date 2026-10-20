# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from full_features import FullFeatureService
from src.jb_quickpanel.services.user_content import UserContentStore


class PictureSymbolTests(unittest.TestCase):
    def test_builtin_favorite_id_survives_different_installation_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            items = []
            with patch("full_features.UserContentStore") as store_type:
                store_type.return_value.list_picture_symbols.return_value = []
                for name in ("first_run", "next_run"):
                    repository = Path(folder) / name
                    (repository / "symbols" / "비전").mkdir(parents=True)
                    (repository / "config").mkdir()
                    (repository / "symbols" / "비전" / "기본.jpg").write_bytes(b"image")
                    (repository / "config" / "config.json").write_text("{}", encoding="utf-8")
                    features = FullFeatureService(repository)
                    item = features.picture_symbol_catalog()[0]["items"][0]
                    self.assertTrue(features.find_picture_symbol(item["key"]).is_file())
                    items.append(item)
            self.assertNotEqual(items[0]["key"], items[1]["key"])
            self.assertEqual(items[0]["favorite_key"], items[1]["favorite_key"])
            self.assertEqual(items[0]["favorite_key"], "builtin:비전/기본.jpg")

    def test_user_picture_symbol_is_copied_renamed_and_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "user_content"
            source = Path(folder) / "내 심볼.png"
            source.write_bytes(b"png-test")
            store = UserContentStore(root)

            first = store.add_picture_symbol(source)
            second = store.add_picture_symbol(source)
            source.unlink()

            listed = store.list_picture_symbols()
            self.assertEqual([item["title"] for item in listed], ["내 심볼", "내 심볼 (2)"])
            self.assertTrue(all(Path(item["file"]).is_file() for item in listed))

            store.update_picture_symbol(first["id"], "수정 심볼")
            copied = Path(store.list_picture_symbols()[0]["file"])
            store.delete_picture_symbol(first["id"])
            self.assertFalse(copied.exists())
            self.assertEqual(store.list_picture_symbols()[0]["id"], second["id"])

    def test_catalog_places_user_symbols_first_and_resolves_their_key(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            repository = base / "repository"
            symbol_folder = repository / "symbols" / "비전"
            config_folder = repository / "config"
            symbol_folder.mkdir(parents=True)
            config_folder.mkdir(parents=True)
            (symbol_folder / "기본.jpg").write_bytes(b"builtin-image")
            (config_folder / "config.json").write_text(
                json.dumps({"settings": {"symbols_root": "symbols"}}),
                encoding="utf-8",
            )

            source = base / "사용자.png"
            source.write_bytes(b"user-image")
            store = UserContentStore(base / "user_content")
            item = store.add_picture_symbol(source)
            features = FullFeatureService(repository)

            with patch("full_features.UserContentStore", return_value=store):
                groups = features.picture_symbol_catalog()
                self.assertEqual(groups[0]["title"], "내 심볼")
                self.assertTrue(groups[0]["items"][0]["user_item"])
                self.assertEqual(groups[1]["title"], "비전")
                resolved = features.find_picture_symbol(f"user:{item['id']}")

            self.assertEqual(resolved, Path(store.list_picture_symbols()[0]["file"]))


if __name__ == "__main__":
    unittest.main()
