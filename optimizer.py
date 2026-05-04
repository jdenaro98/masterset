import math
from itertools import combinations


def optimize(all_card_data):
    """Return a cart selecting one listing per card by total cost, then seller count.

    Primary objective: minimize total cost (price + shipping).
    Secondary objective: minimize the number of unique sellers.
    """
    if not all_card_data:
        return []

    card_names = list(all_card_data.keys())
    all_cards_set = set(card_names)

    # Build per-seller best listing per card.
    seller_cards = {}
    for card, listings in all_card_data.items():
        if not listings:
            continue
        for listing in listings:
            seller = listing.get("seller")
            if not seller:
                continue
            seller_cards.setdefault(seller, {})
            current = seller_cards[seller].get(card)
            if current is None or _listing_preferred(listing, current):
                seller_cards[seller][card] = listing

    if not seller_cards:
        return [{"card": card, "seller": None, "condition": None, "price": None, "shipping": None, "total": None} for card in card_names]

    # Try to find the cart assignment with the lowest total cost first.
    # If multiple assignments tie on cost, choose the one with fewer unique sellers.
    candidate_sellers = sorted(
        seller_cards.keys(),
        key=lambda seller: (sum(listing["total"] for listing in seller_cards[seller].values()), -len(seller_cards[seller]))
    )

    best_seller_set = None
    best_cost = math.inf
    best_seller_count = math.inf

    max_search_sellers = min(len(candidate_sellers), 12)
    for k in range(1, max_search_sellers + 1):
        for sellers in combinations(candidate_sellers[:max_search_sellers], k):
            covered = set()
            for seller in sellers:
                covered |= set(seller_cards[seller].keys())
            if covered != all_cards_set:
                continue
            cost = _assignment_cost(sellers, card_names, seller_cards)
            if cost == math.inf:
                continue
            seller_count = len(set(sellers))
            if cost < best_cost or (cost == best_cost and seller_count < best_seller_count):
                best_cost = cost
                best_seller_count = seller_count
                best_seller_set = set(sellers)

    if best_seller_set is None:
        best_seller_set = _greedy_cost_cover(seller_cards, all_cards_set)

    assignment = _choose_best_assignment(best_seller_set, card_names, seller_cards)

    return [
        {
            "card": card,
            "seller": assignment.get(card, {}).get("seller"),
            "condition": assignment.get(card, {}).get("condition"),
            "price": assignment.get(card, {}).get("price"),
            "shipping": assignment.get(card, {}).get("shipping"),
            "total": assignment.get(card, {}).get("total"),
            "card_url": assignment.get(card, {}).get("card_url"),
            "add_to_cart": assignment.get(card, {}).get("add_to_cart"),
            "add_to_cart_link": assignment.get(card, {}).get("add_to_cart_link"),
            "add_to_cart_payload": assignment.get(card, {}).get("add_to_cart_payload"),
        }
        for card in card_names
    ]


def _listing_preferred(a, b):
    if a["total"] != b["total"]:
        return a["total"] < b["total"]
    return a["shipping"] < b["shipping"]


def _assignment_cost(sellers, card_names, seller_cards):
    cost = 0.0
    for card in card_names:
        best = None
        for seller in sellers:
            listing = seller_cards[seller].get(card)
            if listing is None:
                continue
            if best is None or _listing_preferred(listing, best):
                best = listing
        if best is None:
            return math.inf
        cost += best["total"]
    return cost


def _choose_best_assignment(seller_set, card_names, seller_cards):
    assignment = {}
    for card in card_names:
        best = None
        for seller in seller_set:
            listing = seller_cards[seller].get(card)
            if listing is None:
                continue
            if best is None or _listing_preferred(listing, best):
                best = listing
        if best is not None:
            assignment[card] = best
        else:
            assignment[card] = {
                "seller": None,
                "condition": None,
                "price": None,
                "shipping": None,
                "total": None,
            }
    return assignment


def _greedy_cost_cover(seller_cards, all_cards_set):
    uncovered = set(all_cards_set)
    selected = set()
    while uncovered:
        best_seller = None
        best_cover = set()
        best_score = None
        for seller, cards in seller_cards.items():
            if seller in selected:
                continue
            cover = uncovered & set(cards.keys())
            if not cover:
                continue
            cost = sum(cards[card]["total"] for card in cover)
            avg_cost = cost / len(cover)
            score = (avg_cost, len(cover), cost)
            if best_score is None or score < best_score:
                best_score = score
                best_cover = cover
                best_seller = seller
        if best_seller is None:
            break
        selected.add(best_seller)
        uncovered -= best_cover
    return selected
