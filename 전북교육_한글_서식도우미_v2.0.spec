# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app(v2.0).py'],
    pathex=[
        'C:\\work\\jb_quickpanel\\build_packages',
        'C:\\work\\jb_quickpanel\\build_packages\\win32',
        'C:\\work\\jb_quickpanel\\build_packages\\win32\\lib',
        'C:\\work\\jb_quickpanel\\build_packages\\pywin32_system32',
    ],
    binaries=[
        ('C:\\work\\jb_quickpanel\\build_packages\\pywin32_system32\\pythoncom312.dll', '.'),
        ('C:\\work\\jb_quickpanel\\build_packages\\pywin32_system32\\pywintypes312.dll', '.'),
    ],
    datas=[('config', 'config'), ('blocks_hwp', 'blocks_hwp'), ('thumbs', 'thumbs'), ('forms_hwp', 'forms_hwp'), ('forms_thumbs', 'forms_thumbs'), ('symbols', 'symbols'), ('page_thumbs', 'page_thumbs'), ('table_thumbs', 'table_thumbs'), ('report_format_prompt.txt', '.')],
    hiddenimports=['pythoncom', 'pywintypes', 'win32clipboard', 'win32gui', 'win32process', 'win32api', 'win32con', 'win32timezone', 'PIL._tkinter_finder'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='전북교육_한글_서식도우미_v2.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
