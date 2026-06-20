# PyInstaller spec for the masterset Python backend.
#
# Prerequisites (run once before building):
#   pip install pyinstaller playwright requests
#   playwright install chromium
#
# Build command (from project root):
#   pyinstaller backend_server.spec --distpath dist --workpath build/pyinstaller --noconfirm

import os
import sys
from pathlib import Path

import playwright as _pw

# ── Locate playwright driver ───────────────────────────────────────────────────
pw_dir = Path(_pw.__file__).parent
pw_driver = pw_dir / 'driver'
if not pw_driver.exists():
    raise SystemExit(
        f"\n[spec] ERROR: playwright driver not found at {pw_driver}\n"
        f"[spec] Run:  pip install playwright\n"
    )

# NOTE: Chromium is NOT bundled here — codesigning a nested .app/.framework
# inside PyInstaller's COLLECT step fails on macOS. Instead, the build script
# copies the browser into dist/backend_server/ms-playwright/ after PyInstaller
# finishes, so server.py's PLAYWRIGHT_BROWSERS_PATH still resolves correctly.

# ── Analysis ───────────────────────────────────────────────────────────────────
a = Analysis(
    ['backend/server.py'],
    pathex=['.'],          # project root — lets PyInstaller find cart_create, optimizer
    binaries=[],
    datas=[
        (str(pw_driver),   'playwright/driver'),
        ('art',             'art'),
    ],
    hiddenimports=[
        'playwright',
        'playwright.sync_api',
        'playwright._impl._sync_base',
        'cart_create',
        'optimizer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='backend_server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='backend_server',
)
