import os
import requests
from PIL import Image


# Maps brightness 0–255 to ASCII density (index 0=darkest, -1=lightest)
_ASCII_CHARS = "@#%S?+;:,. "
# Terminal chars are ~2x taller than wide; halving rows preserves visual aspect ratio
_CHAR_ASPECT = 0.5
_TARGET_WIDTH = 80

def main():
    pass
    # Define actual usage of main if using standalone
    # If using as module, then import image_gen and call functions as needed
    
    # Example usage: ASCII generation for entire 1025 pokemon library from .jpg
    # for i in range(1, 1026):
    #     image_path = f"art/images/pokemon/{i:03d}.png"
    #     if os.path.exists(image_path):
    #         plain_path, color_path = image_gen(image_path)
    #         print(f"Generated ASCII art for {image_path} at {plain_path} and {color_path}")
    #     else:
    #         print(f"Image not found: {image_path}")


def image_gen(image_path: str) -> tuple[str, str]:
    """
    Generate ASCII art from an image and save to art/ascii/<name>.txt.

    For images with a transparent background (e.g. Pokemon sprites), transparent
    pixels become spaces so the ASCII shape follows the sprite outline.
    For fully-opaque images (e.g. cards), the output is rectangular.

    Returns a tuple (plain_path, color_path). The color file embeds ANSI 24-bit
    color codes and renders in color when cat-ed in a true-color terminal.
    """
    img = Image.open(image_path)

    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    img = img.convert("RGBA") if has_alpha else img.convert("RGB")

    orig_w, orig_h = img.size
    target_w = _TARGET_WIDTH
    target_h = max(1, int(target_w * (orig_h / orig_w) * _CHAR_ASPECT))

    img_small = img.resize((target_w, target_h), Image.LANCZOS)
    gray = img_small.convert("L")

    n = len(_ASCII_CHARS) - 1
    plain_lines = []
    color_lines = []
    for y in range(target_h):
        plain_row = []
        color_row = []
        for x in range(target_w):
            pixel = img_small.getpixel((x, y))
            if has_alpha and pixel[3] < 128:
                plain_row.append(" ")
                color_row.append(" ")
            else:
                brightness = gray.getpixel((x, y))
                char = _ASCII_CHARS[int(brightness / 255 * n)]
                plain_row.append(char)
                r, g, b = pixel[0], pixel[1], pixel[2]
                color_row.append(f"\033[38;2;{r};{g};{b}m{char}\033[0m")
        plain_lines.append("".join(plain_row))
        color_lines.append("".join(color_row))

    os.makedirs("art/ascii", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(image_path))[0]

    plain_path = os.path.join("art/ascii/pokemon", f"{base_name}.txt")
    with open(plain_path, "w") as f:
        f.write("\n".join(plain_lines))

    color_path = os.path.join("art/ascii/pokemon", f"{base_name}_color.txt")
    with open(color_path, "w") as f:
        f.write("\n".join(color_lines))

    return plain_path, color_path


def fetch_card_image(product_id: int, save_path: str = None) -> bytes:
    url = f"https://tcgplayer-cdn.tcgplayer.com/product/{product_id}_in_1000x1000.jpg"
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0"
        })
    except requests.RequestException as e:
        print(f"Error fetching image for product ID {product_id}: {e}")
        return None
    resp.raise_for_status()
    if save_path:
        with open(save_path, "wb") as f:
            f.write(resp.content)
    return resp.content

def fetch_poke_image(url: str, save_path: str = None) -> bytes:
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) Gecko/20100101 Firefox/150.0",
            "Referer": "http://www.serbii.net/",
        }, timeout=10)
    except requests.RequestException as e:
        print(f"Error fetching image from {url}: {e}")
        return None
    resp.raise_for_status()
    if save_path:
        with open(save_path, "wb") as f:
            f.write(resp.content)
    return resp.content

if __name__ == "__main__":
    main()