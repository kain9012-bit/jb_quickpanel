import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.server import CellSelectionTracker, FEATURES, _auto_title_template_records, _set_target_mode, _style_records, dispatch


class FakeTracker:
    def __init__(self, values, text_selection=False):
        self.values = values
        self.text_selection = text_selection
        self.processing = False

    def range_values(self):
        return self.values

    def has_recorded_text_selection(self):
        return self.text_selection

    def state(self):
        return {"active": self.values is not None}

    def clear(self):
        self.values = None
        self.text_selection = False


class FakeBridge:
    def __init__(self, in_table, text_selection=False):
        self.in_table = in_table
        self.text_selection = text_selection
        self.calls = []

    def has_active_text_selection(self):
        return self.text_selection

    def get_table_cell_addr(self, focus_before=False):
        if not self.in_table:
            raise RuntimeError("not in table")
        return 1, 1, "A1"

    def cleanup_line_spacing(self, adjust_count, cancelled=None):
        self.calls.append(("text", adjust_count))
        return True, "text spacing"

    def cleanup_cell_range_line_spacing(self, *values, adjust_count, cancelled=None):
        self.calls.append(("cells", values, adjust_count))
        return True, "cell spacing"

    def insert_file(self, file_path, preserve_document=False, preserve_section=None):
        self.calls.append(("insert_file", file_path, preserve_document, preserve_section))
        return True, "style inserted"

    def insert_manual_style(self, file_path):
        self.calls.append(("insert_manual_style", file_path))
        return True, "style inserted"
    def apply_charshape(self, **kwargs):
        self.calls.append(("text_charshape", kwargs))
        return True, "text charshape"

    def apply_charshape_to_cell_range(self, *values, **kwargs):
        self.calls.append(("cell_charshape", values, kwargs))
        return True, "cell charshape"

    def insert_text(self, value):
        self.calls.append(("insert_text", value))
        return True, "inserted"

    def cell_trim_current(self):
        before = self.cell_value
        self.cell_value = before.strip()
        return before != self.cell_value

    def cell_affix_current(self, value, *, at_end=False):
        self.cell_value = self.cell_value + value if at_end else value + self.cell_value
        return bool(value)

    def process_recorded_cell_range(self, start_col, start_row, end_col, end_row, transform_func=None, *, cell_operation=None):
        source = ["alpha", "beta"]
        if cell_operation is not None:
            transformed = []
            for value in source:
                self.cell_value = value
                cell_operation()
                transformed.append(self.cell_value)
        else:
            transformed = [transform_func(value) for value in source]
        self.calls.append(("cell_edges" if cell_operation is not None else "cell_text", (start_col, start_row, end_col, end_row), transformed))
        return {"changed": sum(before != after for before, after in zip(source, transformed))}


class CellSelectionContextTests(unittest.TestCase):
    def test_switching_hwp_window_discards_recorded_cell_range(self):
        window = {"hwnd": 101, "pid": 10, "title": "첫 문서.hwp - 한글"}
        bridge = FakeBridge(in_table=True)
        tracker = CellSelectionTracker(bridge)
        with patch("backend.server.ui_get_last_hwp_window", side_effect=lambda: window):
            tracker.recorded_start = (1, 1, "A1")
            tracker.recorded_end = (2, 1, "B1")
            tracker.recorded_context = tracker._selection_context()
            self.assertEqual(tracker.range_values(), (1, 1, 2, 1))
            window = {"hwnd": 202, "pid": 20, "title": "다른 문서.hwp - 한글"}
            self.assertIsNone(tracker.range_values())
            self.assertIsNone(tracker.recorded_start)

    def test_switching_tables_in_same_window_discards_recorded_range(self):
        bridge = FakeBridge(in_table=True)
        anchor = [(0, 5, 0)]
        bridge._current_table_anchor = lambda: anchor[0]
        tracker = CellSelectionTracker(bridge)
        with patch("backend.server.ui_get_last_hwp_window", return_value={
            "hwnd": 101, "pid": 10, "title": "계획서.hwp - 한글",
        }):
            tracker.recorded_start = (1, 1, "A1")
            tracker.recorded_end = (2, 1, "B1")
            tracker.recorded_context = tracker._selection_context()
            anchor[0] = (0, 9, 0)
            self.assertIsNone(tracker.range_values())


class SettingsDispatchTests(unittest.TestCase):
    @patch("backend.server.FEATURES.integration_status", return_value={"settings_dir": "C:/settings"})
    @patch("backend.server.FEATURES.load_settings", return_value={"start_mode": "hwp"})
    @patch("backend.server.settings_path")
    def test_settings_get_reports_existing_user_data(
        self,
        settings_path_mock,
        _load_settings,
        _integration_status,
    ):
        settings_path_mock.return_value.exists.return_value = True

        result = dispatch("settings_get", {}, FakeBridge(False), FakeTracker(None))

        self.assertTrue(result[0])
        self.assertTrue(result[2]["had_user_data"])

    @patch("backend.server.FEATURES.integration_status", return_value={"settings_dir": "C:/settings"})
    @patch("backend.server.FEATURES.load_settings", return_value={"start_mode": "hwp"})
    @patch("backend.server.settings_path")
    def test_settings_get_identifies_fresh_install(
        self,
        settings_path_mock,
        _load_settings,
        _integration_status,
    ):
        settings_path_mock.return_value.exists.return_value = False

        result = dispatch("settings_get", {}, FakeBridge(False), FakeTracker(None))

        self.assertTrue(result[0])
        self.assertFalse(result[2]["had_user_data"])


class SpacingDispatchTests(unittest.TestCase):
    def setUp(self):
        _set_target_mode('hwp')

    def test_partial_text_inside_cell_does_not_expand_to_cells(self):
        for recorded in (False, True):
            with self.subTest(recorded=recorded):
                bridge = FakeBridge(in_table=True, text_selection=not recorded)
                tracker = FakeTracker((1, 1, 2, 2), text_selection=recorded)
                result = dispatch('spacing_cleanup', {}, bridge, tracker)
                self.assertTrue(result[0])
                self.assertEqual(bridge.calls, [('text', 3)])
                self.assertFalse(tracker.processing)

    def test_processing_guard_is_released_on_failure(self):
        tracker = FakeTracker(None)
        bridge = FakeBridge(False)
        def fail(*args, **kwargs):
            self.assertTrue(tracker.processing)
            self.assertTrue(callable(kwargs['cancelled']))
            raise RuntimeError('test failure')
        bridge.cleanup_line_spacing = fail
        with self.assertRaisesRegex(RuntimeError, 'test failure'):
            dispatch('spacing_cleanup', {}, bridge, tracker)
        self.assertFalse(tracker.processing)

    def test_kedufine_does_not_run_spacing_cleanup(self):
        _set_target_mode('kedufine')
        bridge = FakeBridge(False)
        result = dispatch('spacing_cleanup', {}, bridge, FakeTracker(None))
        self.assertFalse(result[0])
        self.assertEqual(bridge.calls, [])
        _set_target_mode('hwp')

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


class CharacterFormattingDispatchTests(unittest.TestCase):
    def setUp(self):
        _set_target_mode("hwp")

    def test_stale_cell_range_does_not_override_text_selection(self):
        bridge = FakeBridge(in_table=False)
        result = dispatch(
            "apply_charshape",
            {"font_name": "함초롬바탕", "font_size_pt": 11},
            bridge,
            FakeTracker((1, 1, 2, 2)),
        )
        self.assertTrue(result[0])
        self.assertEqual(bridge.calls[0][0], "text_charshape")

    def test_text_selection_inside_table_does_not_use_recorded_cells(self):
        bridge = FakeBridge(in_table=True, text_selection=True)
        result = dispatch(
            "apply_charshape",
            {"font_name": "함초롬바탕", "font_size_pt": 11},
            bridge,
            FakeTracker((1, 1, 1, 1), text_selection=True),
        )
        self.assertTrue(result[0])
        self.assertEqual(bridge.calls[0][0], "text_charshape")

    def test_current_table_cursor_uses_recorded_cell_range(self):
        bridge = FakeBridge(in_table=True)
        result = dispatch(
            "apply_charshape",
            {"font_color_rgb": [255, 0, 0]},
            bridge,
            FakeTracker((1, 1, 2, 2)),
        )
        self.assertTrue(result[0])
        self.assertEqual(
            bridge.calls,
            [("cell_charshape", (1, 1, 2, 2), {
                "font_name": None,
                "font_size_pt": None,
                "font_color_rgb": (255, 0, 0),
            })],
        )


class CellTextDispatchTests(unittest.TestCase):
    def setUp(self):
        _set_target_mode("hwp")

    def test_find_replace_uses_recorded_cell_range(self):
        bridge = FakeBridge(in_table=True)
        result = dispatch(
            "cell_text_action",
            {"action": "find_replace", "value": "a", "replacement": "x"},
            bridge,
            FakeTracker((1, 1, 2, 1)),
        )
        self.assertTrue(result[0])
        self.assertEqual(bridge.calls, [("cell_text", (1, 1, 2, 1), ["xlphx", "betx"])])

    def test_prefix_and_suffix_use_recorded_cell_range(self):
        prefix_bridge = FakeBridge(in_table=True)
        prefix_result = dispatch(
            "cell_text_action",
            {"action": "prefix", "value": "-"},
            prefix_bridge,
            FakeTracker((1, 1, 2, 1)),
        )
        self.assertTrue(prefix_result[0])
        self.assertEqual(prefix_bridge.calls, [("cell_edges", (1, 1, 2, 1), ["-alpha", "-beta"])])

        suffix_bridge = FakeBridge(in_table=True)
        suffix_result = dispatch(
            "cell_text_action",
            {"action": "suffix", "value": "*"},
            suffix_bridge,
            FakeTracker((1, 1, 2, 1)),
        )
        self.assertTrue(suffix_result[0])
        self.assertEqual(suffix_bridge.calls, [("cell_edges", (1, 1, 2, 1), ["alpha*", "beta*"])])

    def test_trim_uses_edge_operation_and_existing_cell_range(self):
        bridge = FakeBridge(in_table=True)
        tracker = FakeTracker((1, 1, 2, 1))
        self.assertTrue(dispatch("cell_clean_spaces", {}, bridge, tracker)[0])
        self.assertEqual(bridge.calls, [("cell_edges", (1, 1, 2, 1), ["alpha", "beta"])])
        self.assertFalse(tracker.processing)

    def test_edge_failure_releases_processing_guard(self):
        for command, args in (("cell_clean_spaces", {}), ("cell_text_action", {"action": "prefix", "value": "x"})):
            bridge = FakeBridge(in_table=True)
            tracker = FakeTracker((1, 1, 2, 1))
            def fail(*_args, **_kwargs):
                raise RuntimeError("edge failure")
            bridge.cell_trim_current = fail
            bridge.cell_affix_current = fail
            with self.assertRaisesRegex(RuntimeError, "edge failure"):
                dispatch(command, args, bridge, tracker)
            self.assertFalse(tracker.processing)


class CharacterInsertionDispatchTests(unittest.TestCase):
    def setUp(self):
        _set_target_mode("hwp")

    @patch("backend.server.ui_get_last_hwp_window", return_value={"hwnd": 1234})
    def test_successful_character_insert_returns_target_window(self, _get_hwp):
        bridge = FakeBridge(in_table=False)
        result = dispatch("insert_character", {"value": "※"}, bridge, FakeTracker(None))
        self.assertTrue(result[0])
        self.assertEqual(bridge.calls, [("insert_text", "※")])
        self.assertEqual(result[2]["hwp_hwnd"], 1234)

class StyleDispatchTests(unittest.TestCase):
    def setUp(self):
        _set_target_mode("hwp")
    def test_catalog_includes_all_builtin_styles_with_previews(self):
        result = dispatch("style_catalog", {}, FakeBridge(in_table=False), FakeTracker(None))
        self.assertTrue(result[0])
        builtin_items = [item for item in result[2]["items"] if item["source"] == "builtin"]
        self.assertEqual(len(builtin_items), 7)
        self.assertTrue(all(item["preview"].startswith("data:image/") for item in builtin_items))

    def test_auto_title_catalog_is_role_specific_and_excludes_general_styles(self):
        dedicated = {
            "id": "doc-example",
            "role": "document_title",
            "title": "내 문서제목",
            "file": r"C:\work\document.hwpx",
            "thumb": "",
            "title_token": "DOC",
            "number_token": "",
        }
        with patch(
            "backend.server.UserContentStore.list_auto_title_templates",
            return_value=[dedicated],
        ):
            result = dispatch(
                "auto_title_template_catalog",
                {},
                FakeBridge(in_table=False),
                FakeTracker(None),
            )
        self.assertTrue(result[0])
        items = result[2]["items"]
        self.assertEqual(
            {(item["role"], item["source"]) for item in items},
            {
                ("document_title", "builtin"),
                ("title", "builtin"),
                ("document_title", "user"),
            },
        )
        self.assertTrue(all(item["key"].startswith("auto-title-") for item in items))
        self.assertEqual(
            {item["key"] for item in items if item["title"] == "표 서식 없음"},
            {
                "auto-title-none:document_title",
                "auto-title-none:title",
            },
        )

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
        self.assertEqual(bridge.calls, [("insert_manual_style", record["manual_file_path"])])
        self.assertEqual(record["manual_file_path"].lower().endswith(".hwp"), True)
        self.assertEqual(result[2]["style_key"], record["key"])

    def test_builtin_auto_title_template_keeps_its_existing_hwpx_source(self):
        record = next(item for item in _auto_title_template_records() if item["key"] == "auto-title-builtin:document_title")
        self.assertTrue(record["file_path"].lower().endswith(".hwpx"))


class FormDispatchTests(unittest.TestCase):
    def setUp(self):
        _set_target_mode("hwp")

    def tearDown(self):
        _set_target_mode("hwp")

    def test_insert_form_preserves_content_definitions_without_section(self):
        record = next(item for item in FEATURES.content_records("form") if item["source"] == "builtin")
        bridge = FakeBridge(in_table=False)
        result = dispatch(
            "insert_form",
            {"item_key": record["key"], "mode": "insert"},
            bridge,
            FakeTracker(None),
        )
        self.assertTrue(result[0])
        self.assertEqual(
            bridge.calls,
            [("insert_file", record["file_path"], True, False)],
        )

    def test_user_hwp_form_is_inserted_without_format_change(self):
        with tempfile.TemporaryDirectory() as folder:
            hwp = Path(folder) / "custom.hwp"
            hwp.write_bytes(b"sample")
            record = {"key": "user:custom", "id": "custom", "title": "내 양식", "user_item": True, "file_path": str(hwp)}
            bridge = FakeBridge(in_table=False)
            with patch.object(FEATURES, "find_content", return_value=record):
                ok, _, _ = dispatch("insert_form", {"item_key": "user:custom", "mode": "insert"}, bridge, FakeTracker(None))
            self.assertTrue(ok)
            self.assertEqual(bridge.calls, [("insert_file", str(hwp), True, False)])

    def test_open_form_uses_working_copy_without_inserting(self):
        record = next(item for item in FEATURES.content_records("form") if item["source"] == "builtin")
        bridge = FakeBridge(in_table=False)
        with patch.object(FEATURES, "open_form_working_copy", return_value=r"C:\work\copy.hwpx") as opener:
            result = dispatch(
                "insert_form",
                {"item_key": record["key"], "mode": "new_document"},
                bridge,
                FakeTracker(None),
            )
        self.assertTrue(result[0])
        self.assertEqual(bridge.calls, [])
        self.assertEqual(result[2]["working_path"], r"C:\work\copy.hwpx")
        opener.assert_called_once_with(record)


class UserDataTransferDispatchTests(unittest.TestCase):
    def test_backup_command_returns_created_backup(self):
        backup = {"cancelled": False, "path": r"C:\backup\settings.jbhbackup"}
        with patch.object(FEATURES, "backup_user_data", return_value=backup):
            result = dispatch(
                "user_data_backup",
                {},
                FakeBridge(in_table=False),
                FakeTracker(None),
            )

        self.assertTrue(result[0])
        self.assertEqual(result[2]["backup"], backup)

    def test_restore_command_returns_settings_and_integration(self):
        restored = {
            "cancelled": False,
            "integration": {"startup": True, "start_menu": False},
        }
        settings = {"start_mode": "hwp", "target_mode": "hwp"}
        integration = {"startup": False, "start_menu": True}
        with patch.object(
            FEATURES, "restore_user_data", return_value=(restored, settings)
        ), patch.object(FEATURES, "integration_status", return_value=integration):
            result = dispatch(
                "user_data_restore",
                {},
                FakeBridge(in_table=False),
                FakeTracker(None),
            )

        self.assertTrue(result[0])
        self.assertEqual(result[2]["restore"], restored)
        self.assertEqual(result[2]["settings"]["target_mode"], "hwp")
        self.assertEqual(result[2]["integration"], integration)

if __name__ == "__main__":
    unittest.main()
