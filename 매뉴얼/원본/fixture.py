"""Read only built-in catalogs for manual screenshots; never connect to Hancom."""
import json

from backend.server import (
    FEATURES, _auto_title_template_records, _public_auto_title_item,
    _public_style_item, _style_records,
)

data = {
    "style_catalog": {"items": [_public_style_item(item) for item in _style_records()]},
    "auto_title_template_catalog": {
        "items": [_public_auto_title_item(item) for item in _auto_title_template_records()]
    },
    "form_catalog": {"items": FEATURES.catalog("form")},
    "kedufine_form_catalog": {"items": FEATURES.kedufine_form_catalog()},
    "page_catalog": {"items": FEATURES.catalog("page")},
    "table_catalog": {"items": FEATURES.table_catalog()},
    "character_catalog": {"groups": FEATURES.character_catalog()},
    "picture_symbol_catalog": {"groups": FEATURES.picture_symbol_catalog()},
    "font_catalog": {"fonts": ["휴먼명조", "맑은 고딕", "굴림체", "HY헤드라인M"]},
    "settings": FEATURES.load_settings(),
}
data["settings"].update(
    tutorial_completed=True,
    check_updates_on_startup=False,
    global_hotkeys_enabled=False,
)
print(json.dumps(data, ensure_ascii=False))
