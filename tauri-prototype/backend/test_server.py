import unittest

from backend.server import _style_records, dispatch


class FakeTracker:
    def __init__(self, values):
        self.values = values

    def range_values(self):
        return self.values

    def state(self):
        return {"active": self.values is not None}


class FakeBridge:
    def __init__(self, in_table):
        self.in_table = in_table
        self.calls = []

    def get_table_cell_addr(self, focus_before=False):
        if not self.in_table:
            raise RuntimeError("not in table")
        return 1, 1, "A1"

    def cleanup_line_spacing(self, adjust_count):
        self.calls.append(("text", adjust_count))
        return True, "text spacing"

    def cleanup_cell_range_line_spacing(self, *values, adjust_count):
        self.calls.append(("cells", values, adjust_count))
        return True, "cell spacing"

    def insert_file(self, file_path):
        self.calls.append(("insert_file", file_path))
        return True, "style inserted"


class SpacingDispatchTests(unittest.TestCase):
    def test_stale_cell_range_does_not_override_text_selection(self):
        bridge = FakeBridge(in_table=False)
        result = dispatch("spacing_cleanup", {"adjust_count": 3}, bridge, FakeTracker((1, 1, 2, 2)))
        self.assertTrue(result[0])
        self.assertEqual(bridge.calls, [("text", 3)])

    def test_current_table_cursor_uses_recorded_cell_range(self):
        bridge = FakeBridge(in_table=True)
        result = dispatch("spacing_cleanup", {"adjust_count": 5}, bridge, FakeTracker((1, 1, 2, 2)))
        self.assertTrue(result[0])
        self.assertEqual(bridge.calls, [("cells", (1, 1, 2, 2), 5)])


class StyleDispatchTests(unittest.TestCase):
    def test_catalog_includes_all_builtin_styles_with_previews(self):
        result = dispatch("style_catalog", {}, FakeBridge(in_table=False), FakeTracker(None))
        self.assertTrue(result[0])
        builtin_items = [item for item in result[2]["items"] if item["source"] == "builtin"]
        self.assertEqual(len(builtin_items), 7)
        self.assertTrue(all(item["preview"].startswith("data:image/") for item in builtin_items))

    def test_insert_style_uses_selected_style_file(self):
        record = next(item for item in _style_records() if item["source"] == "builtin")
        bridge = FakeBridge(in_table=False)
        result = dispatch(
            "insert_style",
            {"style_key": record["key"]},
            bridge,
            FakeTracker(None),
        )
        self.assertTrue(result[0])
        self.assertEqual(bridge.calls, [("insert_file", record["file_path"])])
        self.assertEqual(result[2]["style_key"], record["key"])


if __name__ == "__main__":
    unittest.main()
