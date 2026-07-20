import math


def optimize(all_card_data):
    if not all_card_data:
        return []

    # Identity is the dict key (a stable card id — productId[:printing]), NOT the
    # display name: a multi-set/multi-game binder can hold two different cards that
    # share a name (e.g. "Pikachu" from two sets), and keying by name would collapse
    # them into one. The display name rides along on each entry as "card".
    card_ids  = list(all_card_data.keys())
    name_of   = {cid: cd["card_info"]["name"] for cid, cd in all_card_data.items()}

    # 1. For each card, find the cheapest possible total (price + individual shipping)
    #    and keep a reference to that listing so we can fall back to it later.
    market_floor = {}
    floor_listing = {}
    for cid, card_data in all_card_data.items():
        listings = card_data["market_listings"]
        if listings:
            best = min(listings, key=lambda lst: lst["total"])
            market_floor[cid] = best["total"]
            floor_listing[cid] = best
        else:
            market_floor[cid] = math.inf
            floor_listing[cid] = None

    # 2. Build Seller Map: seller → { card_id: best_listing_from_that_seller }
    seller_map = {}
    for cid, card_data in all_card_data.items():
        listings = card_data["market_listings"]
        for listing in listings:
            s_name = listing["seller"]
            if s_name not in seller_map:
                seller_map[s_name] = {}
            if cid not in seller_map[s_name] or listing["total"] < seller_map[s_name][cid]["total"]:
                seller_map[s_name][cid] = listing

    # 3. Greedy: each round pick the seller whose batch saves the most dollars vs.
    #    buying every card in that batch individually at its market floor price.
    #    Only bundle with a seller when it genuinely saves money; otherwise fall back
    #    to individual cheapest listings so we never inflate the total for the sake
    #    of reducing seller count.
    final_assignment = {}
    uncovered_cards = set(card_ids)

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
            full_listing["card"]   = name_of[c]
            full_listing["cardId"] = c
            final_assignment[c] = full_listing
            uncovered_cards.discard(c)

    # Any cards not assigned to a bundled seller go to their individual cheapest listing
    for c in list(uncovered_cards):
        listing = floor_listing.get(c)
        if listing:
            entry = listing.copy()
            entry["card"]   = name_of[c]
            entry["cardId"] = c
            final_assignment[c] = entry
            uncovered_cards.discard(c)

    return [final_assignment.get(cid, _empty_result(name_of[cid], cid)) for cid in card_ids]


def _estimate_shipping(inventory, card_subset):
    """Predicts shipping cost based on TCGPlayer's $5 free-shipping rule."""
    subtotal = sum(inventory[c]["price"] for c in card_subset)
    has_deal = any(inventory[c].get("shipping_deal") for c in card_subset)
    if has_deal and subtotal >= 5.0:
        return 0.0
    return max(inventory[c]["shipping"] for c in card_subset)


def _empty_result(card_name, card_id=None):
    return {
        "card":               card_name,
        "cardId":             card_id,
        "seller":             None,
        "price":              0.0,
        "shipping":           0.0,
        "total":              0.0,
        "sku":                None,
        "sellerKey":          None,
        "custom_listing_key": "N/A",
    }
