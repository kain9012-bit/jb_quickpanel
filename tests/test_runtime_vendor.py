import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.jb_quickpanel.core import runtime


class VendoredPywin32Tests(unittest.TestCase):
    def test_incompatible_vendor_dlls_are_not_added_to_import_path(self):
        with tempfile.TemporaryDirectory() as folder:
            dll_dir = Path(folder) / "vendor" / "pywin32" / "pywin32_system32"
            dll_dir.mkdir(parents=True)
            other_version = "313" if sys.version_info[:2] == (3, 12) else "312"
            for name in ("pythoncom", "pywintypes"):
                (dll_dir / f"{name}{other_version}.dll").touch()
            with patch.object(runtime, "_early_project_base_dir", return_value=folder), patch.object(
                runtime.sys, "path", ["sentinel"]
            ):
                runtime._add_vendor_pywin32_paths()
                self.assertEqual(runtime.sys.path, ["sentinel"])


if __name__ == "__main__":
    unittest.main()
