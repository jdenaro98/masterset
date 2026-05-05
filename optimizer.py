import math
from itertools import combinations


def optimize(all_card_data):
    """Return a cart selecting one listing per card while preferring fewer sellers.

    This optimizer will prefer assignments with fewer unique sellers only when the
    selected listing price for each card is within one standard deviation of that
    card's overall price distribution. Total cost remains the tiebreaker.
    """
    if not all_card_data:
        return []

    card_names = list(all_card_data.keys())
    all_cards_set = set(card_names)
    price_stats = _build_card_price_stats(all_card_data)

    seller_cards = {}
    seller_cards_acceptable = {}
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

            if _listing_within_stddev(listing, card, price_stats):
                seller_cards_acceptable.setdefault(seller, {})
                current_acceptable = seller_cards_acceptable[seller].get(card)
                if current_acceptable is None or _listing_preferred(listing, current_acceptable):
                    seller_cards_acceptable[seller][card] = listing

    if not seller_cards:
        return [{"card": card, "seller": None, "condition": None, "price": None, "shipping": None, "total": None} for card in card_names]

    best_seller_set, seller_cards_used = _find_best_seller_set(card_names, seller_cards_acceptable, seller_cards)
    if best_seller_set is None:
        best_seller_set, seller_cards_used = _find_best_seller_set(card_names, seller_cards, seller_cards)

    assignment = _choose_best_assignment(best_seller_set, card_names, seller_cards_used)

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


def _build_card_price_stats(all_card_data):
    stats = {}
    for card, listings in all_card_data.items():
        prices = [listing["price"] for listing in listings if listing.get("price") is not None]
        if not prices:
            continue
        mean = sum(prices) / len(prices)
        variance = sum((price - mean) ** 2 for price in prices) / len(prices)
        stats[card] = {
            "mean": mean,
            "stddev": math.sqrt(variance),
        }
    return stats


def _listing_within_stddev(listing, card, stats):
    price = listing.get("price")
    if price is None or card not in stats:
        return False
    card_stats = stats[card]
    if card_stats["stddev"] == 0:
        return True
    return abs(price - card_stats["mean"]) <= card_stats["stddev"]


def _find_best_seller_set(card_names, seller_cards, backup_seller_cards):
    if not seller_cards:
        return None, None

    all_cards_set = set(card_names)
    candidate_sellers = sorted(
        seller_cards.keys(),
        key=lambda seller: (
            -len(seller_cards[seller]),
            sum(listing["total"] for listing in seller_cards[seller].values()) / len(seller_cards[seller]),
            sum(listing["total"] for listing in seller_cards[seller].values()),
        ),
    )

    best_set = None
    best_cost = math.inf
    best_seller_count = math.inf
    max_search_sellers = min(len(candidate_sellers), 18)

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
            if seller_count < best_seller_count or (seller_count == best_seller_count and cost < best_cost):
                best_cost = cost
                best_seller_count = seller_count
                best_set = set(sellers)

    if best_set is not None:
        return best_set, seller_cards

    if seller_cards is not backup_seller_cards:
        return _find_best_seller_set(card_names, backup_seller_cards, backup_seller_cards)

    return _greedy_cost_cover(seller_cards, all_cards_set), seller_cards


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
            score = (-len(cover), avg_cost, cost)
            if best_score is None or score < best_score:
                best_score = score
                best_cover = cover
                best_seller = seller
        if best_seller is None:
            break
        selected.add(best_seller)
        uncovered -= best_cover
    return selected
