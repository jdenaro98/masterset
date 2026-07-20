'use strict';
/**
 * The binder — an anonymous, browser-persistent internal cart.
 *
 * Unlike the mid-flow snapshot in app.js (sessionStorage, tab-scoped, wiped on the
 * home screen), the binder lives in localStorage so it survives refreshes and browser
 * restarts like any anonymous shopping cart. It's the source of truth for which cards
 * the user is optimizing; the backend's scraped-listing cache is a rebuildable
 * derivative keyed by the same card id.
 *
 * Shape (localStorage key `masterset:binder`):
 *   {
 *     cards: [{ id, productId, printing, displayName, number,
 *               setId, setName, gameId, gameName }],
 *     filters: { conditions: [...], quals: [...] }   // last-used, persisted
 *   }
 */

const BINDER_KEY = 'masterset:binder';

/**
 * Stable per-card identity, shared with the backend listing cache
 * (see _card_id in backend/server.py). Keeping printing in the key lets two
 * printings of one product coexist instead of colliding.
 */
export function cardId(productId, printing) {
  return `${productId}:${printing || ''}`;
}

function _empty() {
  return { cards: [], filters: { conditions: [], quals: [] } };
}

export function getBinder() {
  try {
    const raw = localStorage.getItem(BINDER_KEY);
    if (!raw) return _empty();
    const parsed = JSON.parse(raw);
    return {
      cards:   Array.isArray(parsed.cards) ? parsed.cards : [],
      filters: parsed.filters || { conditions: [], quals: [] },
    };
  } catch (_) {
    return _empty();
  }
}

function _save(binder) {
  try { localStorage.setItem(BINDER_KEY, JSON.stringify(binder)); } catch (_) {}
}

export function getCards() {
  return getBinder().cards;
}

export function binderCount() {
  return getBinder().cards.length;
}

/**
 * Add cards to the binder, deduped by id. `cards` is an array of
 * { productId, printing, displayName, number, setId, setName, gameId, gameName }.
 * Returns the number actually added (skipping ones already present).
 */
export function addCards(cards) {
  const binder = getBinder();
  const seen = new Set(binder.cards.map(c => c.id));
  let added = 0;
  for (const c of cards) {
    const id = cardId(c.productId, c.printing);
    if (seen.has(id)) continue;
    seen.add(id);
    binder.cards.push({
      id,
      productId:   c.productId,
      printing:    c.printing || null,
      displayName: c.displayName,
      number:      c.number || null,
      setId:       c.setId ?? null,
      setName:     c.setName || '',
      gameId:      c.gameId ?? null,
      gameName:    c.gameName || '',
    });
    added++;
  }
  _save(binder);
  return added;
}

export function removeCard(id) {
  const binder = getBinder();
  binder.cards = binder.cards.filter(c => c.id !== id);
  _save(binder);
  return binder.cards.length;
}

export function clearBinder() {
  const binder = getBinder();
  binder.cards = [];
  _save(binder);
}

export function getFilters() {
  return getBinder().filters || { conditions: [], quals: [] };
}

export function saveBinderFilters(filters) {
  const binder = getBinder();
  binder.filters = {
    conditions: filters.conditions || [],
    quals:      filters.quals || [],
  };
  _save(binder);
}

/** Convert a binder card into the task shape the backend's fetch_listings expects. */
export function toTask(card) {
  return {
    productId:   card.productId,
    printing:    card.printing || null,
    displayName: card.displayName,
    cardId:      card.id,
  };
}
