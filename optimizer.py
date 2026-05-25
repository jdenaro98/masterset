import math


def optimize(all_card_data):
    if not all_card_data:
        return []

    card_names = [card_data["card_info"]["name"] for card_data in all_card_data.values()]

    # 1. Establish the "Market Floor" (Cheapest total for each card)
    market_floor = {}
    for product_id, card_data in all_card_data.items():
        card = card_data["card_info"]["name"]
        listings = card_data["market_listings"]
        if listings:
            market_floor[card] = min(listing["total"] for listing in listings)
        else:
            market_floor[card] = math.inf

    # 2. Build Seller Map: seller → { card_name: best_listing }
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

    # 3. Greedy selection: maximize (coverage_weight - price_penalty - shipping)
    final_assignment = {}
    uncovered_cards = set(card_names)
    selected_sellers = set()

    while uncovered_cards:
        best_seller = None
        best_seller_value = -math.inf

        for s_name, s_inventory in seller_map.items():
            can_provide = uncovered_cards.intersection(s_inventory.keys())
            if not can_provide:
                continue

            price_penalty = sum(s_inventory[c]["price"] - market_floor[c] for c in can_provide)
            potential_shipping = _estimate_shipping(s_inventory, can_provide)
            value_score = len(can_provide) * 2.0 - price_penalty - potential_shipping

            if value_score > best_seller_value:
                best_seller_value = value_score
                best_seller = s_name

        if not best_seller:
            break

        for c in uncovered_cards.intersection(seller_map[best_seller].keys()):
            full_listing = seller_map[best_seller][c].copy()
            full_listing["card"] = c
            final_assignment[c] = full_listing
            uncovered_cards.remove(c)

        selected_sellers.add(best_seller)

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
        "card": card_name,
        "seller": None,
        "price": 0.0,
        "shipping": 0.0,
        "total": 0.0,
        "sku": None,
        "sellerKey": None,
        "custom_listing_key": "N/A",
    }
