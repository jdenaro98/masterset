import math

def optimize(all_card_data):
    if not all_card_data:
        return []

    card_names = list(all_card_data.keys())
    
    # 1. Establish the "Market Floor" (Cheapest total for each card)
    market_floor = {}
    for card, listings in all_card_data.items():
        if listings:
            # We look at the best 'total' (price + shipping) as the baseline
            market_floor[card] = min(l["total"] for l in listings)
        else:
            market_floor[card] = math.inf

    # 2. Build Seller Map
    # Key: Seller Name, Value: { card_name: best_listing_from_this_seller }
    seller_map = {}
    for card, listings in all_card_data.items():
        for l in listings:
            s_name = l["seller"]
            if s_name not in seller_map:
                seller_map[s_name] = {}
            
            # If the seller has multiple listings for the same card (e.g. different conditions),
            # keep only the cheapest one that meets user criteria.
            if card not in seller_map[s_name] or l["total"] < seller_map[s_name][card]["total"]:
                seller_map[s_name][card] = l

    # 3. The Greedy Selection Loop
    final_assignment = {}
    uncovered_cards = set(card_names)
    selected_sellers = set()

    while uncovered_cards:
        best_seller = None
        best_seller_value = -math.inf # We want to maximize "Value" (Savings/Coverage)

        for s_name, s_inventory in seller_map.items():
            # Only look at cards we haven't covered yet
            can_provide = uncovered_cards.intersection(s_inventory.keys())
            if not can_provide:
                continue

            # Calculate Price Penalty: How much extra are we paying compared to the market floor?
            price_penalty = sum(s_inventory[c]["price"] - market_floor[c] for c in can_provide)
            
            # Calculate potential shipping savings
            # If we buy from this seller, we only pay shipping once (or zero if >$5)
            potential_shipping = _estimate_shipping(s_inventory, can_provide)
            
            # VALUE SCORE: 
            # We want high coverage (len) but low price penalty.
            # You can tune the '2.0' multiplier to prefer consolidation more or less.
            coverage_weight = len(can_provide) * 2.0 
            value_score = coverage_weight - price_penalty - potential_shipping

            if value_score > best_seller_value:
                best_seller_value = value_score
                best_seller = s_name

        if not best_seller:
            break # Should not happen unless cards are unfindable

        # Assign the cards
        for c in uncovered_cards.intersection(seller_map[best_seller].keys()):
            full_listing = seller_map[best_seller][c].copy()
            full_listing['card'] = c
            final_assignment[c] = full_listing
            uncovered_cards.remove(c)
        
        selected_sellers.add(best_seller)

    return [final_assignment.get(card, _empty_result(card)) for card in card_names]

def _estimate_shipping(inventory, card_subset):
    """Predicts if shipping will be $0 or $X based on TCGPlayer's $5 rule."""
    subtotal = sum(inventory[c]["price"] for c in card_subset)
    # Check if any item in the subset has the shipping deal flag
    has_deal = any(inventory[c].get("shipping_deal") for c in card_subset)
    
    if has_deal and subtotal >= 5.0:
        return 0.0
    
    # Otherwise, return the max shipping fee among the items
    return max(inventory[c]["shipping"] for c in card_subset)

def _empty_result(card_name):
    return {
        "card": card_name, 
        "seller": None, 
        "price": 0.0, 
        "shipping": 0.0, 
        "total": 0.0, 
        "test_id_attr": None, 
        "custom_listing_key": "N/A"
    }