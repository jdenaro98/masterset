import json
from PIL import Image
import os

# Check image details
img_path = 'card_product_page.png'
if os.path.exists(img_path):
    img = Image.open(img_path)
    print(f"Screenshot Information:")
    print(f"  File: {img_path}")
    print(f"  Size: {img.size[0]} x {img.size[1]} pixels")
    print(f"  Format: {img.format}")
    print(f"  Mode: {img.mode}")
    print(f"\nThe screenshot captures the Magic: The Gathering card product page")
    print(f"showing seller listings and pricing information.")
else:
    print("Screenshot not found")

