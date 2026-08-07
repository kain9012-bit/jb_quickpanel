# -*- coding: utf-8 -*-
import ctypes
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from src.jb_quickpanel.features import registry as feature_registry


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")
MODIFIER_BITS = {
    "Ctrl": MOD_CONTROL,
    "Alt": MOD_ALT,
    "Shift": MOD_SHIFT,
    "Win": MOD_WIN,
}
MODIFIER_ALIASES = {
    "CTRL": "Ctrl",
    "CONTROL": "Ctrl",
    "ALT": "Alt",
    "SHIFT": "Shift",
    "WIN": "Win",
    "WINDOWS": "Win",
}

KEY_NAME_TO_VK = {
    **{chr(code): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(number): ord(str(number)) for number in range(10)},
    **{f"F{number}": 0x6F + number for number in range(1, 25)},
    "Space": 0x20,
    "Enter": 0x0D,
    "Tab": 0x09,
    "Backspace": 0x08,
    "Delete": 0x2E,
    "Insert": 0x2D,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "Left": 0x25,
    "Up": 0x26,
    "Right": 0x27,
    "Down": 0x28,
    "-": 0xBD,
    "=": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    ";": 0xBA,
    "'": 0xDE,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
}
VK_TO_KEY_NAME = {value: key for key, value in KEY_NAME_TO_VK.items()}

KEY_ALIASES = {
    "SPACE": "Space",
    "RETURN": "Enter",
    "ENTER": "Enter",
    "TAB": "Tab",
    "BACKSPACE": "Backspace",
    "BACK_SPACE": "Backspace",
    "DELETE": "Delete",
    "INSERT": "Insert",
    "HOME": "Home",
    "END": "End",
    "PAGEUP": "PageUp",
    "PAGE_UP": "PageUp",
    "PRIOR": "PageUp",
    "PAGEDOWN": "PageDown",
    "PAGE_DOWN": "PageDown",
    "NEXT": "PageDown",
    "LEFT": "Left",
    "UP": "Up",
    "RIGHT": "Right",
    "DOWN": "Down",
    "MINUS": "-",
    "EQUAL": "=",
    "BRACKETLEFT": "[",
    "BRACKETRIGHT": "]",
    "BACKSLASH": "\\",
    "SEMICOLON": ";",
    "APOSTROPHE": "'",
    "COMMA": ",",
    "PERIOD": ".",
    "SLASH": "/",
    "GRAVE": "`",
}


@dataclass(frozen=True)
class HotkeySpec:
    text: str
    modifiers: int
    virtual_key: int
    key_name: str


@dataclass(frozen=True)
class HotkeyAction:
    id: str
    category: str
    label: str
    kind: str
    payload: Any = None
    modes: tuple[str, ...] = feature_registry.ALL_MODES
    requires_target: bool = True


def _canonical_key_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("키를 함께 입력하세요.")
    upper = raw.upper()
    if upper in KEY_ALIASES:
        return KEY_ALIASES[upper]
    if len(raw) == 1 and raw.upper() in KEY_NAME_TO_VK:
        return raw.upper()
    if upper.startswith("F") and upper[1:].isdigit():
        name = f"F{int(upper[1:])}"
        if name in KEY_NAME_TO_VK:
            return name
    raise ValueError(f"지원하지 않는 키입니다: {raw}")


def parse_hotkey(value: str, require_modifier: bool = True) -> HotkeySpec:
    parts = [part.strip() for part in str(value or "").split("+") if part.strip()]
    modifiers = set()
    key_parts = []
    for part in parts:
        modifier = MODIFIER_ALIASES.get(part.upper())
        if modifier:
            modifiers.add(modifier)
        else:
            key_parts.append(part)

    if len(key_parts) != 1:
        raise ValueError("보조키와 일반 키 하나를 함께 입력하세요.")
    if require_modifier and not modifiers:
        raise ValueError("Ctrl, Alt, Shift 또는 Win 중 하나 이상을 함께 사용하세요.")

    key_name = _canonical_key_name(key_parts[0])
    modifier_names = [name for name in MODIFIER_ORDER if name in modifiers]
    modifier_bits = 0
    for name in modifier_names:
        modifier_bits |= MODIFIER_BITS[name]
    text = "+".join(modifier_names + [key_name])
    return HotkeySpec(text, modifier_bits, KEY_NAME_TO_VK[key_name], key_name)


def _pressed_modifier_names(state: int, key_state_reader=None) -> list[str]:
    if key_state_reader is None and os.name == "nt":
        try:
            key_state_reader = ctypes.windll.user32.GetAsyncKeyState
        except Exception:
            key_state_reader = None

    if key_state_reader is not None:
        key_map = (
            ("Ctrl", 0x11),
            ("Alt", 0x12),
            ("Shift", 0x10),
            ("Win", 0x5B),
            ("Win", 0x5C),
        )
        pressed = []
        for name, virtual_key in key_map:
            try:
                is_down = bool(int(key_state_reader(virtual_key)) & 0x8000)
            except Exception:
                is_down = False
            if is_down and name not in pressed:
                pressed.append(name)
        return pressed

    pressed = []
    if state & 0x0004:
        pressed.append("Ctrl")
    if state & 0x0008:
        pressed.append("Alt")
    if state & 0x0001:
        pressed.append("Shift")
    if state & 0x0040:
        pressed.append("Win")
    return pressed


def hotkey_from_tk_event(keycode: int, state: int, keysym: str, key_state_reader=None) -> str | None:
    if int(keycode or 0) in (0x10, 0x11, 0x12, 0x5B, 0x5C):
        return None
    modifier_names = _pressed_modifier_names(state, key_state_reader)
    if not modifier_names:
        return None

    key_name = VK_TO_KEY_NAME.get(int(keycode or 0))
    if key_name is None:
        try:
            key_name = _canonical_key_name(keysym)
        except ValueError:
            return None
    return parse_hotkey("+".join(modifier_names + [key_name])).text


def normalize_bindings(raw: Any, valid_action_ids: Iterable[str]) -> tuple[dict[str, str], dict[str, str]]:
    valid_ids = set(valid_action_ids)
    normalized: dict[str, str] = {}
    invalid: dict[str, str] = {}
    if not isinstance(raw, dict):
        return normalized, invalid
    used: dict[str, str] = {}
    for action_id, value in raw.items():
        action_id = str(action_id or "")
        if action_id not in valid_ids or not str(value or "").strip():
            continue
        try:
            text = parse_hotkey(str(value)).text
        except ValueError as exc:
            invalid[action_id] = str(exc)
            continue
        duplicate = used.get(text)
        if duplicate is not None:
            invalid[action_id] = f"{duplicate} 기능과 같은 단축키입니다."
            continue
        used[text] = action_id
        normalized[action_id] = text
    return normalized, invalid


def _default_register(hwnd: int, hotkey_id: int, modifiers: int, virtual_key: int) -> bool:
    if os.name != "nt":
        return False
    return bool(ctypes.windll.user32.RegisterHotKey(hwnd, hotkey_id, modifiers, virtual_key))


def _default_unregister(hwnd: int, hotkey_id: int) -> bool:
    if os.name != "nt":
        return False
    return bool(ctypes.windll.user32.UnregisterHotKey(hwnd, hotkey_id))


class WindowsGlobalHotkeyRegistry:
    START_ID = 0x4A20

    def __init__(
        self,
        register_func: Callable[[int, int, int, int], bool] | None = None,
        unregister_func: Callable[[int, int], bool] | None = None,
    ):
        self._register_func = register_func or _default_register
        self._unregister_func = unregister_func or _default_unregister
        self._registered: dict[int, str] = {}

    def clear(self, hwnd: int | None) -> None:
        if hwnd:
            for hotkey_id in list(self._registered):
                try:
                    self._unregister_func(int(hwnd), hotkey_id)
                except Exception:
                    pass
        self._registered.clear()

    def replace(self, hwnd: int, bindings: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
        self.clear(hwnd)
        registered: dict[str, str] = {}
        failures: dict[str, str] = {}
        for offset, (action_id, value) in enumerate(bindings.items()):
            try:
                spec = parse_hotkey(value)
            except ValueError as exc:
                failures[action_id] = str(exc)
                continue
            hotkey_id = self.START_ID + offset
            try:
                success = self._register_func(
                    int(hwnd),
                    hotkey_id,
                    spec.modifiers | MOD_NOREPEAT,
                    spec.virtual_key,
                )
            except Exception as exc:
                success = False
                failures[action_id] = str(exc)
            if success:
                self._registered[hotkey_id] = action_id
                registered[action_id] = spec.text
            elif action_id not in failures:
                failures[action_id] = "다른 프로그램에서 사용 중이거나 Windows가 예약한 조합입니다."
        return registered, failures

    def action_for_message_id(self, hotkey_id: int) -> str | None:
        return self._registered.get(int(hotkey_id))

    @property
    def count(self) -> int:
        return len(self._registered)


DIRECT_HOTKEY_FEATURE_ACTIONS = (
    *feature_registry.TOP_ROW_ACTIONS,
    feature_registry.CELL_CLEAN_SPACE_ACTION,
    feature_registry.CELL_EXCEL_PASTE_ACTION,
    feature_registry.TABLE_INSERT_IMAGES_ACTION,
    feature_registry.TABLE_REFIT_IMAGES_ACTION,
    *feature_registry.TEXT_SPACING_ACTIONS,
)


def build_hotkey_actions(table_tools, symbols_text) -> tuple[HotkeyAction, ...]:
    actions: list[HotkeyAction] = []
    seen_ids = set()

    def add(action: HotkeyAction) -> None:
        if action.id in seen_ids:
            return
        seen_ids.add(action.id)
        actions.append(action)

    add(HotkeyAction("app.toggle_window", "프로그램", "서식도우미 열기/숨기기", "app", requires_target=False))

    for feature in DIRECT_HOTKEY_FEATURE_ACTIONS:
        if feature.id.startswith("char_spacing"):
            category = "글자 작업"
        elif feature.id.startswith("cell_"):
            category = "셀 정리"
        elif feature.id.startswith("table_"):
            category = "표 작업"
        else:
            category = "서식"
        add(
            HotkeyAction(
                f"feature:{feature.id}",
                category,
                feature.label,
                "feature",
                feature.id,
                feature.modes,
                feature.id != "copy_report_prompt",
            )
        )

    for item in table_tools or []:
        action_id = str(item.get("action_id") or "")
        if not action_id:
            continue
        add(
            HotkeyAction(
                f"table:{action_id}",
                "표 작업",
                str(item.get("title") or action_id).replace("\n", " "),
                "table",
                action_id,
            )
        )

    for color in feature_registry.TEXT_COLOR_ACTIONS:
        rgb_text = ",".join(str(value) for value in color.rgb)
        add(HotkeyAction(f"font-color:{rgb_text}", "글자 작업", f"글자색 {color.label}", "font_color", color))

    for font in feature_registry.TEXT_FONT_ROWS:
        modes = tuple(
            mode
            for mode in feature_registry.ALL_MODES
            if font.font_name not in feature_registry.HIDDEN_TEXT_FONTS_BY_MODE.get(mode, set())
        )
        add(HotkeyAction(f"font:{font.font_name}", "글자 작업", f"글꼴 {font.font_name}", "font", font.font_name, modes))
        for size in font.sizes:
            add(
                HotkeyAction(
                    f"font-size:{font.font_name}:{size}",
                    "글자 작업",
                    f"{font.font_name} {size}pt",
                    "font_size",
                    (font.font_name, size),
                    modes,
                )
            )

    unique_symbols = set()
    if isinstance(symbols_text, dict):
        for group_name, values in symbols_text.items():
            for value in values or []:
                text = str(value)
                if not text or text in unique_symbols:
                    continue
                unique_symbols.add(text)
                encoded = "-".join(f"{ord(char):x}" for char in text)
                add(HotkeyAction(f"insert-text:{encoded}", "문자표", f"{text}  ({group_name})", "insert_text", text))

    return tuple(actions)
