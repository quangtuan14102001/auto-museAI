# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

project_dir = os.path.abspath(SPECPATH)
venv_dir = os.path.join(project_dir, ".venv")
site_packages = os.path.join(venv_dir, "Lib", "site-packages")

playwright_driver_dir = os.path.join(site_packages, "playwright", "driver")

datas = [
    (os.path.join(project_dir, "config", "defaults", "project_config.json"), "config"),
    (os.path.join(project_dir, "assets"), "assets"),
    (os.path.join(project_dir, "bin"), "bin"),
]

if os.path.exists(playwright_driver_dir):
    datas.append((playwright_driver_dir, os.path.join("playwright", "driver")))

localappdata = os.environ.get("LOCALAPPDATA", "")
ms_playwright = os.path.join(localappdata, "ms-playwright")
if os.path.exists(ms_playwright):
    target_items = ["chromium-1243", "ffmpeg-1011"]
    for item in target_items:
        full_item = os.path.join(ms_playwright, item)
        if os.path.exists(full_item) and os.path.isdir(full_item):
            datas.append((full_item, os.path.join("playwright", "driver", "package", ".local-browsers", item)))

hiddenimports = [
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "playwright",
    "playwright.async_api",
    "playwright.sync_api",
    "playwright._impl._driver",
    "edge_tts",
    "aiohttp",
    "requests",
    "json",
    "shutil",
    "uuid",
    "subprocess",
    "sqlite3",
    "base64",
    "urllib.parse",
    "utils.proxy_utils",
    "core.version",
    "core.media_output",
    "ui.dialogs.create_video_dialog",
    "ui.dialogs.film_dialog",
    "core.film_project",
    "workers.film_worker",
    "utils.film_media",
]

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AutoMuseAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'assets', 'logo.ico'),
)

