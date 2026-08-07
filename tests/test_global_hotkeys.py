import json
import unittest
from pathlib import Path

from src.jb_quickpanel.features import registry
from src.jb_quickpanel.features.global_hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    WindowsGlobalHotkeyRegistry,
    build_hotkey_actions,
    hotkey_from_tk_event,
    normalize_bindings,
    parse_hotkey,
)


ROOT = Path(__file__).resolve().parents[1]


class GlobalHotkeyParsingTests(unittest.TestCase):
    def test_normalizes_modifier_order_and_key_name(self):
        spec = parse_hotkey("shift+control+alt+a")

        self.assertEqual(spec.text, "Ctrl+Alt+Shift+A")
        self.assertEqual(spec.modifiers, MOD_CONTROL | MOD_ALT | MOD_SHIFT)
        self.assertEqual(spec.virtual_key, ord("A"))

    def test_requires_a_modifier_and_one_regular_key(self):
        with self.assertRaises(ValueError):
            parse_hotkey("A")
        with self.assertRaises(ValueError):
            parse_hotkey("Ctrl+Alt")

    def test_builds_hotkey_from_actual_modifier_key_state(self):
        def ctrl_shift_reader(virtual_key):
            return 0x8000 if virtual_key in (0x11, 0x10) else 0

        def ctrl_only_reader(virtual_key):
            return 0x8000 if virtual_key == 0x11 else 0

        self.assertEqual(
            hotkey_from_tk_event(ord("1"), 0x2000D, "exclam", ctrl_shift_reader),
            "Ctrl+Shift+1",
        )
        self.assertEqual(
            hotkey_from_tk_event(ord("A"), 0x2000D, "a", ctrl_only_reader),
            "Ctrl+A",
        )

    def test_filters_duplicates_and_invalid_action_ids(self):
        normalized, invalid = normalize_bindings(
            {
                "first": "Alt+Ctrl+1",
                "second": "Ctrl+Alt+1",
                "missing": "Ctrl+Alt+2",
                "third": "Q",
            },
            {"first", "second", "third"},
        )

        self.assertEqual(normalized, {"first": "Ctrl+Alt+1"})
        self.assertIn("second", invalid)
        self.assertIn("third", invalid)


class WindowsGlobalHotkeyRegistryTests(unittest.TestCase):
    def test_registers_dispatches_and_unregisters_hotkeys(self):
        calls = []
        unregistered = []

        def register(hwnd, hotkey_id, modifiers, virtual_key):
            calls.append((hwnd, hotkey_id, modifiers, virtual_key))
            return virtual_key != ord("B")

        hotkeys = WindowsGlobalHotkeyRegistry(register, lambda hwnd, hotkey_id: unregistered.append((hwnd, hotkey_id)) or True)
        registered, failures = hotkeys.replace(101, {"a": "Ctrl+Alt+A", "b": "Ctrl+Alt+B"})

        self.assertEqual(registered, {"a": "Ctrl+Alt+A"})
        self.assertIn("b", failures)
        self.assertEqual(hotkeys.action_for_message_id(hotkeys.START_ID), "a")
        self.assertTrue(calls[0][2] & MOD_NOREPEAT)

        hotkeys.clear(101)
        self.assertEqual(unregistered, [(101, hotkeys.START_ID)])
        self.assertEqual(hotkeys.count, 0)


class GlobalHotkeyCatalogTests(unittest.TestCase):
    def test_catalog_contains_current_direct_actions_with_unique_ids(self):
        config = json.loads((ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        table_tools = registry.with_current_table_tools(config["table_tools"])
        actions = build_hotkey_actions(table_tools, config["symbols"])
        action_ids = {action.id for action in actions}

        self.assertEqual(len(action_ids), len(actions))
        self.assertIn("app.toggle_window", action_ids)
        self.assertIn("feature:char_spacing_cleanup_level_1", action_ids)
        self.assertIn("table:제목셀설정", action_ids)
        self.assertIn("font:굴림체", action_ids)
        self.assertIn("insert-text:203b", action_ids)


if __name__ == "__main__":
    unittest.main()
