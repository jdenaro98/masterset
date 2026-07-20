'use strict';
/**
 * Application flow — home → game → set → card select → binder.
 *
 * The old single-pass funnel ended at a per-set optimizer + cart handoff. Now card
 * selection feeds a persistent **binder** (see binder.js): the user picks cards from
 * any number of sets/games, and the binder page (the former dynamic optimizer) is the
 * single landing spot where the whole binder is priced, filtered, and handed off to a
 * TCGPlayer cart. Global home/binder nav icons (NavController) let the user jump
 * between the flow and the binder from anywhere.
 */

import './style.css';
import { connect, call, on, off } from './api.js';
import * as binder from './binder.js';
import {
  applyTheme,
  runSplash,
  showMainScreen,
  showGridSelectWithSearch,
  showAutocomplete,
  showMultiSelect,
  showProgress,
  showFilterProgress,
  showBinder,
  showCartProgress,
  showCartResult,
  showConfirm,
  buildSummary,
  showLogScreen,
  waitForKey,
  triggerScreenNav,
  pauseScreenKeys,
  resumeScreenKeys,
} from './ui.js';

// ── Flow-state persistence ──────────────────────────────────────────────────
// Refreshing the browser mid-flow (picking cards) should drop the user back where
// they were rather than restarting. We snapshot just enough to resume — game/set ids
// and the in-progress card selection — to sessionStorage (tab-scoped, never outlives
// the tab). The home screen always clears it. A `{ step: 'binder' }` marker means the
// user was on the binder page, so a refresh there resumes the binder (whose contents
// live durably in localStorage, not here).
const FLOW_STATE_KEY = 'masterset:flowState';

function saveFlowState(state) {
  try { sessionStorage.setItem(FLOW_STATE_KEY, JSON.stringify(state)); } catch (_) {}
}
function loadFlowState() {
  try {
    const raw = sessionStorage.getItem(FLOW_STATE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}
function clearFlowState() {
  try { sessionStorage.removeItem(FLOW_STATE_KEY); } catch (_) {}
}

// ── Nav chrome controller ────────────────────────────────────────────────────
// Owns the persistent home/binder icons (declared in index.html, outside #app so
// they survive screen swaps). A click resolves the active screen's promise with a
// { __nav } sentinel via triggerScreenNav; during the selection flow a guard confirm
// protects unsaved progress first.
const NavController = {
  homeBtn:   null,
  binderBtn: null,
  badge:     null,
  guard:     false,

  init() {
    this.homeBtn   = document.getElementById('nav-home');
    this.binderBtn = document.getElementById('nav-binder');
    this.badge     = document.getElementById('nav-binder-badge');
    this.homeBtn.addEventListener('click',   () => this._go('home',   'Home'));
    this.binderBtn.addEventListener('click', () => this._go('binder', 'Binder'));
    this.updateBadge();
  },

  configure({ home = false, binder: showBinderIcon = false, guard = false } = {}) {
    if (this.homeBtn)   this.homeBtn.hidden   = !home;
    if (this.binderBtn) this.binderBtn.hidden = !showBinderIcon;
    this.guard = guard;
    this.updateBadge();
  },

  updateBadge() {
    if (!this.badge) return;
    const n = binder.binderCount();
    this.badge.textContent = String(n);
    this.badge.hidden = n === 0;
  },

  async _go(target, label) {
    if (this.guard) {
      // Detach the underlying screen's key handlers so its Enter doesn't also fire
      // while the guard modal is open, then restore them if the user stays.
      pauseScreenKeys();
      const ok = await showConfirm(`Leave your current selection and go to ${label}?`);
      resumeScreenKeys();
      if (!ok) return;
    }
    triggerScreenNav(target);
  },
};

// A nav-sentinel { __nav } from an interruptible screen maps to a flow outcome.
function navOutcome(nav) { return nav === 'binder' ? 'binder' : 'home'; }

// ── Boot ───────────────────────────────────────────────────────────────────
async function boot() {
  NavController.init();
  const resumeState = loadFlowState();
  NavController.configure({ home: false, binder: false });
  const log = showLogScreen('Connecting to masterset backend…');

  try {
    await connect();
    log.log('Connected.');
  } catch (err) {
    log.header('Cannot reach backend.');
    log.muted(err.message);
    log.muted('');
    log.muted('Make sure the backend server is running:');
    log.muted('  cd backend && python api.py');
    return;
  }

  // Mid-flow refresh: skip the splash/home screen and jump straight back in.
  if (resumeState) {
    if (resumeState.step === 'binder') {
      await runBinder();
      return mainLoop();
    }
    const result = await runCardSelection(resumeState);
    if (result === 'exit') { clearFlowState(); showExitScreen(); return; }
    if (result === 'binder') await runBinder();
    return mainLoop();
  }

  // Splash: fetch theme (random Pokémon), apply CSS theme, run canvas shimmer
  log.log('Loading theme…');
  let theme;
  try {
    theme = await call('get_theme', {});
  } catch (err) {
    log.muted(`Warning: could not load theme (${err.message})`);
    theme = { artContent: '', pokemonName: '', primary: [180, 180, 200], secondary: [140, 190, 220], accent: [130, 200, 180] };
  }

  applyTheme(theme.primary, theme.secondary, theme.accent);
  await runSplash(theme.artContent, theme.primary, theme.pokemonName);

  await mainLoop();
}

// ── Main loop (home screen → game select → set select → ...) ──────────────
async function mainLoop() {
  while (true) {
    // Being at the home screen means no flow is in progress — clearing here is the
    // one choke point that guarantees a home-screen refresh always replays the splash.
    clearFlowState();
    NavController.configure({ home: false, binder: true, guard: false });
    const action = await showMainScreen();

    if (action && action.__nav) {
      if (action.__nav === 'binder') await runBinder();
      continue;                                   // 'home' from home = stay
    }
    if (action === 'restart') {
      // Restart App: re-run the splash screen, then loop back to the home page.
      NavController.configure({ home: false, binder: false });
      let theme;
      try {
        theme = await call('get_theme', {});
      } catch (_err) {
        continue;
      }
      applyTheme(theme.primary, theme.secondary, theme.accent);
      await runSplash(theme.artContent, theme.primary, theme.pokemonName);
      continue;
    }
    // 'launch' runs the card-selection flow
    const result = await runCardSelection();
    if (result === 'exit') { clearFlowState(); showExitScreen(); return; }
    if (result === 'binder') { await runBinder(); continue; }
    // 'home' / 'restart' (from within the flow) loops back to the main screen
  }
}

function showExitScreen() {
  const app = document.getElementById('app');
  app.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#555;font-family:monospace">Goodbye.</div>';
}

// ── Card selection flow ────────────────────────────────────────────────────
// Ends at the "add to binder?" prompt (returns 'binder' on yes). `resume` (optional)
// short-circuits already-completed steps after a mid-flow refresh:
// { gameId, selectedGame, setId, selectedSet, selectedCardNames }.
async function runCardSelection(resume = null) {
  let selectedGame, gameId;

  if (resume && resume.gameId) {
    ({ selectedGame, gameId } = resume);
  } else {
    // ── 1. Game selection ──────────────────────────────────────────────────
    const log = showLogScreen('Fetching game categories…');
    let categories;
    try {
      categories = await call('fetch_categories', {});
    } catch (err) {
      log.header('Error loading game categories.');
      log.muted(err.message);
      await waitForKey('Press Enter to go back.');
      return 'restart';
    }

    const gameNames = Object.keys(categories).sort();
    NavController.configure({ home: true, binder: true, guard: true });
    selectedGame = await showGridSelectWithSearch(
      gameNames,
      'Select a game:',
      { cols: 3, extraKeys: { r: '__restart__', q: '__exit__' } },
    );

    if (selectedGame && selectedGame.__nav) return navOutcome(selectedGame.__nav);
    if (!selectedGame) return 'restart';
    if (selectedGame === '__restart__') return 'restart';
    if (selectedGame === '__exit__')    return 'exit';

    gameId = categories[selectedGame];
  }

  // Checkpoint: game is picked. A refresh from here on resumes past this step.
  saveFlowState({ gameId, selectedGame, step: 'game' });

  let selectedSet, setId;

  if (resume && resume.setId) {
    ({ selectedSet, setId } = resume);
  } else {
    // ── 2. Set filtering / loading ─────────────────────────────────────────
    const filterLog = showLogScreen(`Loading sets for ${selectedGame}…`);
    filterLog.muted('Checking for cached set list…');

    let sets;
    try {
      const cacheRes = await call('check_filter_cache', { gameId });

      if (cacheRes.cached) {
        filterLog.log('Using cached set list.');
        const rawSets = await call('fetch_sets', { gameId });
        const filterRes = await call('filter_sets', { gameId, sets: rawSets });
        sets = filterRes.sets;
      } else {
        // Probe sets for price guide data — streaming progress
        const rawSets = await call('fetch_sets', { gameId });
        const setNames = Object.keys(rawSets);

        if (!setNames.length) {
          filterLog.header('No sets found for this game.');
          await waitForKey('Press Enter to go back.');
          return 'restart';
        }

        filterLog.log(`Found ${setNames.length} sets. Probing for price data…`);
        const { onComplete, onDebug } = showFilterProgress(setNames.length);

        const progressHandler = msg => {
          if (msg.type === 'probe_progress') onComplete(msg.set || '');
        };
        const debugHandler = msg => {
          if (msg.type === 'backend_log') onDebug(msg.text || '');
        };
        on('probe_progress', progressHandler);
        on('backend_log',    debugHandler);

        try {
          const filterRes = await call('filter_sets', { gameId, sets: rawSets });
          sets = filterRes.sets;
        } finally {
          off('probe_progress', progressHandler);
          off('backend_log',    debugHandler);
        }
      }
    } catch (err) {
      showLogScreen('Error loading sets.').muted(err.message);
      await waitForKey('Press Enter to go back.');
      return 'restart';
    }

    const setNames = Object.keys(sets).sort();
    if (!setNames.length) {
      showLogScreen('No sets available for this game.').muted('');
      await waitForKey('Press Enter to go back.');
      return 'restart';
    }

    // ── 3. Set selection ───────────────────────────────────────────────────
    NavController.configure({ home: true, binder: true, guard: true });
    selectedSet = await showAutocomplete(
      setNames,
      `Select a set (${selectedGame}):`,
      { showRefreshBtn: true },
    );

    if (selectedSet && selectedSet.__nav) return navOutcome(selectedSet.__nav);
    if (!selectedSet) return 'restart';

    if (selectedSet === '__refresh__') {
      // Force re-fetch with no cache
      const refreshLog = showLogScreen('Refreshing set list…');
      try {
        const rawSets = await call('fetch_sets', { gameId });
        const names   = Object.keys(rawSets);
        const { onComplete } = showFilterProgress(names.length);
        const ph = msg => { if (msg.type === 'probe_progress') onComplete(msg.set || ''); };
        on('probe_progress', ph);
        try {
          const r = await call('filter_sets', { gameId, sets: rawSets, force: true });
          sets = r.sets;
        } finally {
          off('probe_progress', ph);
        }
      } catch (err) {
        refreshLog.muted(err.message);
        await waitForKey('Press Enter.');
        return 'restart';
      }
      return runCardSelection({ gameId, selectedGame }); // restart set selection with fresh data
    }

    setId = sets[selectedSet];
  }

  // Checkpoint: set is picked. A refresh during card loading resumes to card selection.
  saveFlowState({ gameId, selectedGame, setId, selectedSet, step: 'set' });

  // ── 4. Card loading ────────────────────────────────────────────────────── (always re-run: cheap and backend-cached)
  const cardLog = showLogScreen(`Loading cards from ${selectedSet}…`);
  let cardResult;
  try {
    cardResult = await call('fetch_cards', { setId, gameId });
  } catch (err) {
    cardLog.header('Error fetching cards.');
    cardLog.muted(err.message);
    await waitForKey('Press Enter to go back.');
    return 'restart';
  }

  const cardMap  = cardResult.cards || {};
  const allCards = Object.keys(cardMap);
  if (!allCards.length) {
    cardLog.header('No cards found for this set.');
    await waitForKey('Press Enter to go back.');
    return 'restart';
  }

  const itemMeta  = allCards.map(name => cardMap[name]);
  const baseState = { gameId, selectedGame, setId, selectedSet };

  // ── 5. Card multi-select → "add to binder?" ──────────────────────────────
  let lastSelection = resume && resume.selectedCardNames;
  while (true) {
    NavController.configure({ home: true, binder: true, guard: true });
    const selectResult = await showMultiSelect(
      allCards,
      `Select cards from ${selectedSet}:`,
      {
        itemMeta,
        initialSelected: lastSelection,
        onSelectionChange: names => saveFlowState({ ...baseState, step: 'cards', selectedCardNames: names }),
      },
    );

    if (selectResult && selectResult.__nav) return navOutcome(selectResult.__nav);
    if (selectResult.action === 'exit')    return 'exit';
    if (selectResult.action === 'restart') return 'restart';

    const chosenCards = selectResult.selected;
    if (!chosenCards.length) {
      const back = await showConfirm('No cards selected. Go back to card selection?');
      if (back) { lastSelection = []; continue; }
      return 'home';
    }

    const n = chosenCards.length;
    const addIt = await showConfirm(`Add ${n} card${n === 1 ? '' : 's'} from ${selectedSet} to your binder?`);
    if (!addIt) { lastSelection = chosenCards; continue; }   // No → back to card page, selection intact

    const cardsToAdd = chosenCards.map(name => {
      const meta = cardMap[name] || {};
      return {
        productId:   meta.productId,
        printing:    meta.printing,
        displayName: name,
        number:      meta.number,
        setId,
        setName:     selectedSet,
        gameId,
        gameName:    selectedGame,
      };
    });
    binder.addCards(cardsToAdd);
    NavController.updateBadge();
    return 'binder';
  }
}

// ── Binder page ──────────────────────────────────────────────────────────────
// Ensures listings for the whole binder are scraped (delta only), then loops the
// binder screen, reacting to filter changes / deletes (re-optimize in place) and
// refresh / clear / confirm-cart actions.
async function runBinder() {
  NavController.configure({ home: true, binder: false, guard: false });
  saveFlowState({ step: 'binder' });

  while (true) {
    const cards = binder.getCards();
    if (!cards.length) { await showBinderEmpty(); return; }

    // Scrape only cards we don't already have cached (survives a backend restart,
    // which empties the cache → everything counts as missing → full re-scrape).
    if (await ensureBinderListings(cards) === 'error') return;

    const cardIds = cards.map(c => c.id);

    let filterOptions = { conditions: [], sellerQuals: [] };
    try {
      const fo = await call('get_filter_options', { cardIds });
      filterOptions = { conditions: fo.conditions || [], sellerQuals: fo.sellerQuals || [] };
    } catch (_) {}

    const saved          = binder.getFilters();
    const defaultFilters = { conditions: saved.conditions || [], quals: saved.quals || [] };

    const optLog = showLogScreen('Optimizing binder…');
    let optimizeResult;
    try {
      optimizeResult = await call('optimize_filtered', {
        conditions:  defaultFilters.conditions,
        sellerQuals: defaultFilters.quals,
        cardIds,
      });
    } catch (err) {
      optLog.header('Optimizer error.');
      optLog.muted(err.message);
      await waitForKey('Press Enter to go back.');
      return;
    }

    const firstCart   = optimizeResult.firstCart || optimizeResult.cart || [];
    const defaultCart = optimizeResult.cart      || firstCart;
    const overrides   = optimizeResult.overrides || [];

    let logHandler;
    const logHandlerFn = msg => { if (msg.type === 'backend_log' && logHandler) logHandler(msg.text); };
    on('backend_log', logHandlerFn);

    NavController.configure({ home: true, binder: false, guard: false });
    const result = await showBinder(firstCart, defaultCart, filterOptions, defaultFilters, {
      cards,
      initialOverrides: overrides,
      onLog:           fn => { logHandler = fn; },
      onFiltersChange: f  => binder.saveBinderFilters(f),
      onDeleteCard:    id => { binder.removeCard(id); NavController.updateBadge(); },
    });

    off('backend_log', logHandlerFn);

    if (result && result.__nav) return;              // home icon (binder icon hidden here)

    const action = result.action;
    if (action === 'home' || action === 'empty') {
      if (action === 'empty') { await showBinderEmpty(); }
      return;
    }
    if (action === 'refresh') {
      const tasks = binder.getCards().map(binder.toTask);
      if (await scrapeListings(tasks, { merge: true }) === 'error') return;
      continue;                                      // re-optimize + re-show
    }
    if (action === 'clear') {
      const yes = await showConfirm('Clear your entire binder? This removes all cards.');
      if (yes) { binder.clearBinder(); NavController.updateBadge(); await showBinderEmpty(); return; }
      continue;                                      // re-show binder unchanged
    }
    if (action === 'confirm') {
      const outcome = await createCartAndHandoff(result);
      if (outcome === 'cancelled') continue;         // back to binder (contents kept)
      return;                                        // handed off → home (binder kept)
    }
    return;
  }
}

// Empty-binder landing (delete-all, last-card delete, or cold open via the icon).
async function showBinderEmpty() {
  NavController.configure({ home: true, binder: false, guard: false });
  saveFlowState({ step: 'binder' });
  const log = showLogScreen('Your binder is empty');
  log.muted('');
  log.muted('Pick some cards from a set to start building your binder,');
  log.muted('then optimize the whole thing here in one place.');
  log.muted('');
  await waitForKey('Press Enter to go to the home screen.');
}

// Fetch listings for any binder cards not already cached (delta), merging into the
// backend cache. Returns 'ok' or 'error' (error screen already shown).
async function ensureBinderListings(cards) {
  let cached;
  try { cached = await call('check_listings_cache', {}); } catch (_) { cached = { productIds: [] }; }
  const have    = new Set(cached.productIds || []);
  const missing = cards.filter(c => !have.has(c.id));
  if (!missing.length) return 'ok';
  return scrapeListings(missing.map(binder.toTask), { merge: true });
}

// Run the listings scrape with the streaming progress screen.
async function scrapeListings(tasks, { merge = false } = {}) {
  const { onComplete, onPage, onDebug } = showProgress(tasks.length);
  const handler = msg => {
    if (msg.type === 'progress')           onComplete(msg.card || '');
    if (msg.type === 'card_page_progress') onPage(msg.card || '', msg.fetched || 0);
    if (msg.type === 'backend_log')        onDebug(msg.text || '');
  };
  on('progress',           handler);
  on('card_page_progress', handler);
  on('backend_log',        handler);
  try {
    await call('fetch_listings', { tasks, merge });
  } catch (err) {
    off('progress', handler); off('card_page_progress', handler); off('backend_log', handler);
    showLogScreen('Error fetching listings.').muted(err.message);
    await waitForKey('Press Enter to go back.');
    return 'error';
  }
  off('progress', handler); off('card_page_progress', handler); off('backend_log', handler);
  return 'ok';
}

// Confirm + build the TCGPlayer cart, then show the bookmarklet handoff. The binder
// is intentionally NOT cleared, so the user can return and keep working.
// Returns 'cancelled' if the user backs out of the confirm, else 'done'.
async function createCartAndHandoff(result) {
  const finalCart = result.cart;
  const cartTitle = result.cartTitle || 'Cart';
  const summary   = result.summary   || buildSummary(finalCart);

  const lines = [
    `Cart: ${cartTitle}`,
    `${summary.cards} items  •  ${summary.sellers} sellers`,
    `Subtotal: $${summary.rawCost.toFixed(2)}  •  Shipping: ~$${summary.shipping.toFixed(2)}  •  Total: ~$${summary.total.toFixed(2)}`,
    '',
    'Add these items to your TCGPlayer cart?',
  ].join('\n');

  const confirmed = await showConfirm(lines);
  if (!confirmed) return 'cancelled';

  const cartProgress = showCartProgress(finalCart.length, {
    cartTitle,
    cards:    summary.cards,
    sellers:  summary.sellers,
    rawCost:  summary.rawCost,
    shipping: summary.shipping,
    total:    summary.total,
  });

  const cartProgressHandler = msg => {
    if (msg.type === 'cart_progress') cartProgress(msg.card || '');
  };
  on('cart_progress', cartProgressHandler);

  let cartResult;
  try {
    cartResult = await call('create_cart', { optimizedCart: finalCart });
  } catch (err) {
    off('cart_progress', cartProgressHandler);
    showLogScreen('Cart creation failed.').muted(err.message);
    await waitForKey('Press Enter to go back.');
    return 'done';
  }
  off('cart_progress', cartProgressHandler);

  showCartResult(cartResult);
  await waitForKey('Press Enter to return to the home screen. Your binder is saved.');
  return 'done';
}

// ── Entry ──────────────────────────────────────────────────────────────────
boot().catch(err => {
  const app = document.getElementById('app');
  app.innerHTML = `<div style="padding:16px;color:#ff8888;font-family:monospace">Fatal error: ${err.message}</div>`;
  console.error(err);
});
