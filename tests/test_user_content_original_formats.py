import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.jb_quickpanel.services.user_content import UserContentError, UserContentStore


HWP_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def make_source(path):
    if path.suffix == ".hwp":
        path.write_bytes(HWP_SIGNATURE + b"sample")
    else:
        with ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/hwp+zip")
            archive.writestr("Contents/section0.xml", "<section/>")


@pytest.mark.parametrize("kind", ["style", "form"])
@pytest.mark.parametrize("extension", [".hwp", ".hwpx"])
def test_user_file_keeps_original_format(tmp_path, kind, extension):
    source = tmp_path / f"source{extension}"
    make_source(source)
    store = UserContentStore(tmp_path / "data")
    item = store.add_file(kind, "example", source)
    listed = store.list_items(kind)[0]
    copied = Path(listed["file"])
    assert copied.suffix == extension
    assert copied.read_bytes() == source.read_bytes()
    assert len(list(copied.parent.glob("*"))) == 1
    assert not item.get("kedufine_file")
    store.delete_item(kind, item["id"])
    assert not copied.exists()


@pytest.mark.parametrize("extension", [".hwp", ".hwpx"])
def test_kedufine_form_rejects_file_registration(tmp_path, extension):
    source = tmp_path / f"source{extension}"
    make_source(source)
    store = UserContentStore(tmp_path / "data")
    with pytest.raises(UserContentError, match="본문 텍스트"):
        store.add_file("kedufine_form", "example", source)
    assert not store.list_items("kedufine_form")


def test_kedufine_text_form_saves_updates_and_reloads_without_file(tmp_path):
    store = UserContentStore(tmp_path / "data")
    item = store.add_kedufine_text_form("example", "internal", "1. 관련: 예시\r\n2. 내용")
    listed = UserContentStore(store.root).list_items("kedufine_form")[0]
    assert listed["file"] == ""
    assert listed["category"] == "internal"
    assert listed["body"] == "1. 관련: 예시\n2. 내용"
    assert not (store.root / "kedufine_forms").exists()

    store.update_kedufine_text_form(item["id"], "updated", "outgoing", "본문")
    updated = UserContentStore(store.root).list_items("kedufine_form")[0]
    assert updated["title"] == "updated"
    assert updated["category"] == "outgoing"
    assert updated["body"] == "본문"
    store.delete_item("kedufine_form", item["id"])
    assert store.list_items("kedufine_form") == []


def test_kedufine_text_form_validates_category_and_body(tmp_path):
    store = UserContentStore(tmp_path / "data")
    with pytest.raises(UserContentError, match="분류"):
        store.add_kedufine_text_form("example", "unknown", "본문")
    with pytest.raises(UserContentError, match="본문"):
        store.add_kedufine_text_form("example", "internal", "  ")
    assert store.list_items("kedufine_form") == []


def test_existing_paired_and_legacy_files_are_not_migrated(tmp_path):
    root = tmp_path / "data"
    (root / "styles").mkdir(parents=True)
    (root / "forms").mkdir()
    make_source(root / "styles" / "old.hwp")
    make_source(root / "styles" / "old.hwpx")
    make_source(root / "forms" / "old.hwp")
    original = {
        "version": 5,
        "styles": [{"id": "s1", "title": "old style", "file": "styles/old.hwpx", "kedufine_file": "styles/old.hwp"}],
        "forms": [{"id": "f1", "title": "old form", "file": "forms/old.hwp"}],
    }
    raw = json.dumps(original)
    (root / "library.json").write_text(raw)
    store = UserContentStore(root)
    assert Path(store.list_items("style")[0]["kedufine_file"]).suffix == ".hwp"
    assert Path(store.list_items("form")[0]["file"]).suffix == ".hwp"
    assert (root / "library.json").read_text() == raw
    assert not (root / "forms" / "old.hwpx").exists()


def test_legacy_kedufine_file_is_preserved_when_text_is_added(tmp_path):
    root = tmp_path / "data"
    (root / "kedufine_forms").mkdir(parents=True)
    old_file = root / "kedufine_forms" / "old.hwp"
    make_source(old_file)
    (root / "library.json").write_text(json.dumps({
        "version": 5,
        "kedufine_forms": [{"id": "old", "title": "옛 양식", "file": "kedufine_forms/old.hwp"}],
    }), encoding="utf-8")
    store = UserContentStore(root)
    store.update_kedufine_text_form("old", "옛 양식", "outgoing", "1. 관련: 예시")
    raw = json.loads((root / "library.json").read_text(encoding="utf-8"))["kedufine_forms"][0]
    assert "file" not in raw
    assert raw["legacy_file"] == "kedufine_forms/old.hwp"
    assert old_file.is_file()
