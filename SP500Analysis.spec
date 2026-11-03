# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['sp500_analysis.py'],
    pathex=[],
    binaries=[],
    datas=[('S&P 500 과거 데이터.csv', '.')],
    hiddenimports=['matplotlib.backends.backend_tkagg'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6', 'PySide6', 'shiboken6', 'scipy', 'seaborn', 'IPython', 'openpyxl', 'selenium', 'pygame'],
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
    name='SP500Analysis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\sp500.ico'],
)
