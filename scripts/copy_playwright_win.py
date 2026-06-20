"""
Copy Playwright browser binaries into the PyInstaller bundle after it's built.

Windows Playwright cache: %LOCALAPPDATA%\ms-playwright
"""

import os
import pathlib
import shutil
import sys

local_app_data = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData" / "Local")
PW_CACHE = pathlib.Path(local_app_data) / "ms-playwright"
DEST_BASE = pathlib.Path("dist/backend_server/_internal/ms-playwright")

DEST_BASE.mkdir(parents=True, exist_ok=True)

copied = []
for pattern in ("chromium-*", "chromium_headless_shell-*"):
    matches = sorted(PW_CACHE.glob(pattern))
    if not matches:
        print(f"WARNING: no match for {pattern} in {PW_CACHE}", file=sys.stderr)
        continue
    src = matches[-1]
    dest = DEST_BASE / src.name
    shutil.copytree(str(src), str(dest), dirs_exist_ok=True)
    print(f"Copied {src.name} -> {dest}")
    copied.append(src.name)

if not copied:
    print("ERROR: no Playwright browser directories were copied", file=sys.stderr)
    sys.exit(1)
