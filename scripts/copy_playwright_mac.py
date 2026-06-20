"""
Copy Playwright browser binaries into the PyInstaller bundle after it's built.

PyInstaller's _MEIPASS (sys._MEIPASS) is the _internal/ subdirectory of the
one-folder bundle, so PLAYWRIGHT_BROWSERS_PATH resolves to:
  dist/backend_server/_internal/ms-playwright/

Playwright 1.40+ uses chromium_headless_shell for headless mode, so both
chromium-* and chromium_headless_shell-* must be present.
"""

import pathlib
import shutil
import sys

PW_CACHE = pathlib.Path.home() / "Library" / "Caches" / "ms-playwright"
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
