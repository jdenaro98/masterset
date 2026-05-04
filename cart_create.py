import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from playwright_stealth.stealth import Stealth

COOKIE_EDITOR_EXTENSION_ID = "hlkenndednhfkekhgcdicdfddnkalmdm"
DEFAULT_EXTENSION_PATH = Path("extensions/cookie-editor")
DEFAULT_COOKIE_EXPORT_NAME = "cart_cookies.json"
REPO_ROOT = Path(__file__).resolve().parent


def create_cart(
    optimized_cart: List[Dict[str, Any]],
    extension_dir: Optional[str] = None,
    export_path: Optional[str] = None,
) -> Optional[str]:
    """Add optimized listings to a headful Chromium session and export cart cookies."""
    if not optimized_cart:
        print("No optimized cart items were provided.")
        return None

    extension_root = Path(extension_dir).expanduser() if extension_dir else DEFAULT_EXTENSION_PATH
    extension_path = str(extension_root) if extension_root.exists() else None
    if extension_dir and not extension_root.exists():
        print(f"Warning: cookie editor extension folder not found at {extension_root}. Export will fall back to direct cookie save.")

    export_file = Path(export_path).expanduser() if export_path else REPO_ROOT / DEFAULT_COOKIE_EXPORT_NAME
    export_file.parent.mkdir(parents=True, exist_ok=True)

    profile_dir = Path.cwd() / ".playwright_cart_profile"
    profile_dir.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        browser_context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=_build_chromium_args(extension_path),
            viewport={"width": 1400, "height": 1000},
        )

        try:
            page = browser_context.new_page()
            stealth = Stealth()
            stealth.apply_stealth_sync(page)

            page.goto("https://www.tcgplayer.com", wait_until="networkidle")
            time.sleep(1)

            for item in optimized_cart:
                _add_cart_item(page, item)

            exported_with_extension = False
            if extension_path:
                exported_with_extension = _attempt_extension_cookie_export(browser_context, extension_root, export_file)

            if not exported_with_extension:
                _export_cookies_direct(browser_context, export_file)

            print(f"Cookies exported to {export_file}")
            return str(export_file)
        finally:
            browser_context.close()


def _build_chromium_args(extension_path: Optional[str]) -> List[str]:
    args = [
        "--start-maximized",
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
    ]
    if extension_path:
        args.extend([
            f"--disable-extensions-except={extension_path}",
            f"--load-extension={extension_path}",
        ])
    return args


def _add_cart_item(page: Page, item: Dict[str, Any]) -> bool:
    card_url = item.get("card_url")
    seller = (item.get("seller") or "").strip()
    condition = (item.get("condition") or "").strip()
    name = item.get("card") or "card"

    if not card_url:
        print(f"Skipping {name}: missing card_url.")
        return False

    print(f"Adding {name!r} from seller {seller!r} condition {condition!r}...")
    page.goto(card_url, wait_until="networkidle")
    page.wait_for_timeout(2000)
    _dismiss_overlays(page)

    try:
        page.wait_for_selector(".listing-item", timeout=12000)
    except PlaywrightTimeoutError:
        print(f"  No listing rows found for {name}. Skipping.")
        return False

    rows = page.locator(".listing-item")
    if rows.count() == 0:
        print(f"  No listing rows found for {name} after load. Skipping.")
        return False

    if _find_and_click_listing(rows, seller, condition):
        return True

    if seller:
        print(f"  Exact match not found for {name}; trying seller-only fallback.")
        if _find_and_click_listing(rows, seller, ""):
            return True

    print(f"  Could not locate an add-to-cart button for {name}.")
    return False


def _find_and_click_listing(rows: Any, seller: str, condition: str) -> bool:
    provided_seller = seller.lower()
    provided_condition = condition.lower()

    for index in range(rows.count()):
        row = rows.nth(index)
        row.scroll_into_view_if_needed()
        time.sleep(0.2)

        seller_name = (row.locator(".seller-info__name").text_content() or "").strip()
        condition_text = (row.locator(".listing-item__listing-data__info__condition").text_content() or "").strip()
        seller_name_lower = seller_name.lower()
        condition_text_lower = condition_text.lower()

        if provided_seller and provided_seller not in seller_name_lower:
            continue
        if provided_condition and provided_condition not in condition_text_lower:
            continue

        if _click_add_to_cart(row):
            print(f"  Added listing from {seller_name!r} ({condition_text}).")
            row.page.wait_for_timeout(1000)
            return True
    return False


def _click_add_to_cart(row: Any) -> bool:
    button = row.locator(
        "button[aria-label*='Add to cart'], button:has-text('Add to Cart'), a:has-text('Add to Cart'), button[data-testid^='add-to-cart__submit'], .add-to-cart button"
    )
    if button.count() > 0:
        try:
            button.first.scroll_into_view_if_needed()
            button.first.click(force=True)
            return True
        except Exception:
            pass

    button = row.locator("button:has-text('Add')")
    if button.count() > 0:
        try:
            button.first.scroll_into_view_if_needed()
            button.first.click(force=True)
            return True
        except Exception:
            pass

    return False


def _dismiss_overlays(page: Page) -> None:
    overlay_buttons = page.locator("button:has-text('No Thanks'), button:has-text('Close'), button[aria-label*='Close']")
    if overlay_buttons.count() > 0:
        try:
            overlay_buttons.first.click()
        except Exception:
            pass

    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


def _attempt_extension_cookie_export(context: BrowserContext, extension_root: Path, export_file: Path) -> bool:
    manifest = _load_extension_manifest(extension_root)
    if not manifest:
        return False

    ui_path = _find_extension_ui_path(manifest, extension_root)
    if not ui_path:
        return False

    extension_url = f"chrome-extension://{COOKIE_EDITOR_EXTENSION_ID}/{ui_path}"
    try:
        page = context.new_page()
        page.goto(extension_url, wait_until="load")
        page.wait_for_timeout(1000)

        if page.locator("button:has-text('Export')").count() > 0:
            with page.expect_download(timeout=15000) as download_info:
                page.locator("button:has-text('Export')").first.click()
            download = download_info.value
            download.save_as(str(export_file))
            page.close()
            print(f"Exported cookies via extension to {export_file}")
            return True
    except Exception:
        pass

    return False


def _load_extension_manifest(extension_root: Path) -> Optional[Dict[str, Any]]:
    manifest_path = extension_root / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except Exception:
        return None


def _find_extension_ui_path(manifest: Dict[str, Any], extension_root: Path) -> Optional[str]:
    if manifest.get("action") and manifest["action"].get("default_popup"):
        return manifest["action"]["default_popup"]
    if manifest.get("browser_action") and manifest["browser_action"].get("default_popup"):
        return manifest["browser_action"]["default_popup"]
    if manifest.get("options_ui") and manifest["options_ui"].get("page"):
        return manifest["options_ui"]["page"]
    if manifest.get("options_page"):
        return manifest["options_page"]

    for candidate in ["popup.html", "index.html", "main.html", "options.html"]:
        if (extension_root / candidate).exists():
            return candidate
    return None


def _export_cookies_direct(context: BrowserContext, export_file: Path) -> None:
    cookies = context.cookies()
    filtered = [cookie for cookie in cookies if "tcgplayer.com" in cookie.get("domain", "")]
    if not filtered:
        filtered = cookies
    export_file.write_text(json.dumps(filtered, indent=2))
