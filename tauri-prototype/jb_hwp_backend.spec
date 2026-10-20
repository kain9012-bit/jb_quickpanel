# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

prototype_root = Path(SPECPATH).resolve()
repository_root = prototype_root.parent
backend_root = prototype_root / "backend"

resource_names = (
    "assets",
    "blocks_hwp",
    "config",
    "forms_hwp",
    "forms_thumbs",
    "page_thumbs",
    "symbols",
    "table_thumbs",
    "thumbs",
)
datas = [(str(repository_root / name), name) for name in resource_names]
datas.append((str(repository_root / "report_format_prompt.txt"), "."))

hiddenimports = ["win32timezone"]
hiddenimports += collect_submodules("win32com")
hiddenimports += collect_submodules("win32comext")

a = Analysis(
    [str(backend_root / "server.py")],
    pathex=[str(repository_root), str(backend_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="jb_hwp_backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
