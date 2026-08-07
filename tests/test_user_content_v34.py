import json
import tempfile
import unittest
from pathlib import Path

from src.jb_quickpanel.services.user_content import UserContentError, UserContentStore


class UserContentPreviewTests(unittest.TestCase):
    def test_preview_is_copied_replaced_cleared_and_deleted_with_item(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            source = Path(folder) / "source.hwp"
            preview_png = Path(folder) / "preview.png"
            preview_jpg = Path(folder) / "replacement.jpg"
            source.write_bytes(b"hwp")
            preview_png.write_bytes(b"png-preview")
            preview_jpg.write_bytes(b"jpg-preview")
            store = UserContentStore(root)

            item = store.add_file("style", "Preview style", source, preview_path=preview_png)
            listed = store.list_items("style")[0]
            first_preview = Path(listed["thumb"])
            copied_hwp = Path(listed["file"])
            self.assertEqual(first_preview.read_bytes(), b"png-preview")

            store.update_preview("style", item["id"], preview_jpg)
            second_preview = Path(store.list_items("style")[0]["thumb"])
            self.assertEqual(second_preview.read_bytes(), b"jpg-preview")
            self.assertFalse(first_preview.exists())

            store.update_preview("style", item["id"], None)
            self.assertEqual(store.list_items("style")[0]["thumb"], "")
            self.assertFalse(second_preview.exists())

            store.update_preview("style", item["id"], preview_png)
            final_preview = Path(store.list_items("style")[0]["thumb"])
            store.delete_item("style", item["id"])
            self.assertFalse(copied_hwp.exists())
            self.assertFalse(final_preview.exists())

    def test_old_library_without_symbol_groups_is_migrated_in_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            root.mkdir(parents=True)
            (root / "library.json").write_text(
                json.dumps({"version": 1, "styles": [], "forms": [], "pages": []}),
                encoding="utf-8",
            )
            store = UserContentStore(root)
            self.assertEqual(store.list_symbol_groups(), [])


class UserSymbolGroupTests(unittest.TestCase):
    def test_symbol_groups_preserve_order_deduplicate_and_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            store = UserContentStore(root)
            first = store.add_symbol_group("Favorites", "☆, ★\n☐ ☆")
            second = store.add_symbol_group("Brackets", "「 」")

            self.assertEqual(
                [(item["title"], item["chars"]) for item in store.list_symbol_groups()],
                [("Favorites", ["☆", "★", "☐"]), ("Brackets", ["「", "」"])],
            )

            store.update_symbol_group(first["id"], "Frequent", "※ ✓")
            with self.assertRaisesRegex(UserContentError, "같은 이름"):
                store.update_symbol_group(second["id"], "Frequent", "○")

            reloaded = UserContentStore(root)
            self.assertEqual(reloaded.list_symbol_groups()[0]["chars"], ["※", "✓"])
            reloaded.delete_symbol_group(second["id"])
            self.assertEqual([item["title"] for item in reloaded.list_symbol_groups()], ["Frequent"])


if __name__ == "__main__":
    unittest.main()
