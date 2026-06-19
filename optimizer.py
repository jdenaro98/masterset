import math


def optimize(all_card_data):
    if not all_card_data:
        return []

    card_names = [card_data["card_info"]["name"] for card_data in all_card_data.values()]

    # 1. For each card, find the cheapest possible total (price + individual shipping)
    #    and keep a reference to that listing so we can fall back to it later.
    market_floor = {}
    floor_listing = {}
    for product_id, card_data in all_card_data.items():
        card = card_data["card_info"]["name"]
        listings = card_data["market_listings"]
        if listings:
            best = min(listings, key=lambda lst: lst["total"])
            market_floor[card] = best["total"]
            floor_listing[card] = best
        else:
            market_floor[card] = math.inf
            floor_listing[card] = None

    # 2. Build Seller Map: seller → { card_name: best_listing_from_that_seller }
    seller_map = {}
    for product_id, card_data in all_card_data.items():
        card = card_data["card_info"]["name"]
        listings = card_data["market_listings"]
        for listing in listings:
            s_name = listing["seller"]
            if s_name not in seller_map:
                seller_map[s_name] = {}
            if card not in seller_map[s_name] or listing["total"] < seller_map[s_name][card]["total"]:
                seller_map[s_name][card] = listing

    # 3. Greedy: each round pick the seller whose batch saves the most dollars vs.
    #    buying every card in that batch individually at its market floor price.
    #    Only bundle with a seller when it genuinely saves money; otherwise fall back
    #    to individual cheapest listings so we never inflate the total for the sake
    #    of reducing seller count.
    final_assignment = {}
    uncovered_cards = set(card_names)

    while uncovered_cards:
        best_seller = None
        best_savings = 0.0  # threshold: only accept a seller if savings > 0

        for s_name, s_inventory in seller_map.items():
            can_provide = uncovered_cards.intersection(s_inventory.keys())
            if not can_provide:
                continue

            # What this batch actually costs from this seller
            batch_price    = sum(s_inventory[c]["price"] for c in can_provide)
            batch_shipping = _estimate_shipping(s_inventory, can_provide)
            actual_cost    = batch_price + batch_shipping

            # What it would cost to buy those same cards individually at their cheapest
            baseline_cost = sum(market_floor[c] for c in can_provide)

            savings = baseline_cost - actual_cost

            if savings > best_savings:
                best_savings = savings
                best_seller  = s_name

        if not best_seller:
            break  # no seller saves money vs. buying individually — stop bundling

        for c in list(uncovered_cards.intersection(seller_map[best_seller].keys())):
            full_listing = seller_map[best_seller][c].copy()
            full_listing["card"] = c
            final_assignment[c] = full_listing
            uncovered_cards.discard(c)

    # Any cards not assigned to a bundled seller go to their individual cheapest listing
    for c in list(uncovered_cards):
        listing = floor_listing.get(c)
        if listing:
            entry = listing.copy()
            entry["card"] = c
            final_assignment[c] = entry
            uncovered_cards.discard(c)

    return [final_assignment.get(card, _empty_result(card)) for card in card_names]


def _estimate_shipping(inventory, card_subset):
    """Predicts shipping cost based on TCGPlayer's $5 free-shipping rule."""
    subtotal = sum(inventory[c]["price"] for c in card_subset)
    has_deal = any(inventory[c].get("shipping_deal") for c in card_subset)
    if has_deal and subtotal >= 5.0:
        return 0.0
    return max(inventory[c]["shipping"] for c in card_subset)


def _empty_result(card_name):
    return {
        "card":               card_name,
        "seller":             None,
        "price":              0.0,
        "shipping":           0.0,
        "total":              0.0,
        "sku":                None,
        "sellerKey":          None,
        "custom_listing_key": "N/A",
    }
