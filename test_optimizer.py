"""
Replay the optimizer against a listings_debug.json dump and print a cost summary.

Usage:
    python test_optimizer.py [listings_debug.json]
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimizer


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "listings_debug.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} cards from {path}\n")

    cart = optimizer.optimize(data)

    total_price    = sum(r.get("price", 0) or 0 for r in cart)
    total_shipping = sum(r.get("shipping", 0) or 0 for r in cart)
    total_cost     = total_price + total_shipping
    sellers        = {r["seller"] for r in cart if r.get("seller")}
    missing        = [r["card"] for r in cart if not r.get("seller")]

    print(f"{'Card':<50} {'Seller':<30} {'Price':>7} {'Ship':>6} {'Total':>7}")
    print("-" * 105)
    for r in sorted(cart, key=lambda x: x.get("seller") or ""):
        name     = (r["card"] or "")[:49]
        seller   = (r["seller"] or "N/A")[:29]
        price    = r.get("price", 0) or 0
        shipping = r.get("shipping", 0) or 0
        total    = price + shipping
        print(f"{name:<50} {seller:<30} ${price:>6.2f} ${shipping:>5.2f} ${total:>6.2f}")

    print("-" * 105)
    print(f"{'TOTAL':<50} {'':<30} ${total_price:>6.2f} ${total_shipping:>5.2f} ${total_cost:>6.2f}")
    print(f"\nSellers used: {len(sellers)}")
    if missing:
        print(f"No listing found for: {', '.join(missing)}")

    # Compare against naive best-individual-price baseline
    baseline = 0.0
    for card_data in data.values():
        listings = card_data.get("market_listings", [])
        if listings:
            baseline += min(l["total"] for l in listings)

    print(f"\nNaive baseline (cheapest per card, each shipped individually): ${baseline:.2f}")
    print(f"Optimized total:                                                ${total_cost:.2f}")
    delta = total_cost - baseline
    sign  = "+" if delta >= 0 else "-"
    print(f"Difference vs baseline:                                         {sign}${abs(delta):.2f}")


if __name__ == "__main__":
    main()
