import json
import zipfile
from pathlib import Path


def test_builtin_styles_and_forms_are_real_hwpx_files():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "config" / "config.json").read_text(encoding="utf-8"))
    for item in (*config["blocks"], *config["forms"]):
        path = root / item["file"]
        assert path.suffix == ".hwpx"
        assert path.is_file(), path
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None, path
            assert any(name.startswith("Contents/section") for name in archive.namelist()), path
    for item in config["blocks"]:
        path = root / item["kedufine_file"]
        assert path.suffix == ".hwp"
        assert path.is_file(), path
        assert path.read_bytes()[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", path
