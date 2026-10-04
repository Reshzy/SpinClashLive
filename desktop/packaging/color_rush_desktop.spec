# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Color Rush Live operator console.

Build (Windows):
  uv sync --extra desktop
  uv run pyinstaller desktop/packaging/color_rush_desktop.spec

The bundle must not include .env, Google credentials, SQL URLs, or simulation dumps.
"""

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ

a = Analysis(
    ["../src/color_rush_desktop/__main__.py"],
    pathex=["../src"],
    binaries=[],
    datas=[],
    hiddenimports=["keyring.backends.Windows", "PySide6.QtWebSockets"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "alembic",
        "psycopg",
        "sqlalchemy",
        "redis",
        "color_rush",
        "pytest",
        "mypy",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ColorRushLive",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ColorRushLive",
)
