# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — ASIC Verification & Analysis Suite
# Build:  pyinstaller main.spec  (from the asic_suite/ directory)

block_cipher = None

# Pillow native DLLs that PyInstaller cannot auto-resolve from conda
_CONDA_BIN = r'C:\Users\royf1\anaconda3\envs\varification_model\Library\bin'
_PIL_DLLS = [
    'libjpeg.dll',
    'tiff.dll',
    'openjp2.dll',
    'freetype.dll',
    'lcms2.dll',
    'libpng16.dll',
    'libwebp.dll',
    'libwebpdecoder.dll',
    'libwebpdemux.dll',
    'libwebpmux.dll',
    'zlib.dll',
    'zstd.dll',
]
import os as _os
_binaries_extra = [
    (_os.path.join(_CONDA_BIN, dll), '.')
    for dll in _PIL_DLLS
    if _os.path.exists(_os.path.join(_CONDA_BIN, dll))
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=_binaries_extra,
    datas=[
        ('tau_logo.png',  '.'),
        ('app_icon.ico',  '.'),
        ('core',          'core'),
        ('ui',            'ui'),
        ('styles',        'styles'),
    ],
    hiddenimports=[
        'PyQt6.QtPrintSupport',
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_agg',
        'PIL._imaging',
        'cv2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ASIC_Suite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ASIC_Suite',
)
