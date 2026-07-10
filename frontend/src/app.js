'use strict';
/**
 * Application flow — mirrors main.js orchestration, now browser-native.
 */

import './style.css';
import { connect, call, on, off, ART_BASE } from './api.js';
import {
  applyTheme,
  parseArtColors,
  runSplash,
  showMainScreen,
  showGridSelectWithSearch,
  showAutocomplete,
  showMultiSelect,
  showProgress,
  showFilterProgress,
  showDynamicOptimizer,
  showCartProgress,
  showCartResult,
  showConfirm,
  buildSummary,
  calcShipping,
  showLogScreen,
  waitForKey,
} from './ui.js';

// ── Boot ───────────────────────────────────────────────────────────────────
async function boot() {
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
    const action = await showMainScreen();
    if (action === 'restart') {
      // Restart App: re-run the splash screen, then loop back to the home page.
      let theme;
      try {
        theme = await call('get_theme', {});
      } catch (err) {
        continue;
      }
      applyTheme(theme.primary, theme.secondary, theme.accent);
      await runSplash(theme.artContent, theme.primary, theme.pokemonName);
      continue;
    }
    // 'launch' runs the card-selection flow
    const result = await runCardSelection();
    if (result === 'exit') { showExitScreen(); return; }
    // 'restart' (from within the flow) loops back to main screen
  }
}

function showExitScreen() {
  const app = document.getElementById('app');
  app.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#555;font-family:monospace">Goodbye.</div>';
}

// ── Card selection flow ────────────────────────────────────────────────────
async function runCardSelection() {
  // ── 1. Game selection ────────────────────────────────────────────────────
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
  const selectedGame = await showGridSelectWithSearch(
    gameNames,
    'Select a game:',
    { cols: 3, extraKeys: { r: '__restart__', q: '__exit__' } },
  );

  if (!selectedGame) return 'restart';
  if (selectedGame === '__restart__') return 'restart';
  if (selectedGame === '__exit__')    return 'exit';

  const gameId = categories[selectedGame];

  // ── 2. Set filtering / loading ───────────────────────────────────────────
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

  // ── 3. Set selection ─────────────────────────────────────────────────────
  const selectedSet = await showAutocomplete(
    setNames,
    `Select a set (${selectedGame}):`,
    { showRefreshBtn: true },
  );

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
    return runCardSelection(); // restart the whole flow with fresh data
  }

  const setId = sets[selectedSet];

  // ── 4. Card loading ──────────────────────────────────────────────────────
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

  const itemMeta = allCards.map(name => cardMap[name]);

  // ── 5. Card multi-select ─────────────────────────────────────────────────
  const selectResult = await showMultiSelect(
    allCards,
    `Select cards from ${selectedSet}:`,
    { itemMeta },
  );

  if (selectResult.action === 'exit')    return 'exit';
  if (selectResult.action === 'restart') return 'restart';

  const chosenCards = selectResult.selected;
  if (!chosenCards.length) {
    const ok = await showConfirm('No cards selected. Go back to card selection?');
    return ok ? 'restart' : 'exit';
  }

  // Build task list for the backend's fetch_listings handler.
  const tasks = chosenCards.map(name => {
    const meta = cardMap[name] || {};
    return { productId: meta.productId, printing: meta.printing, displayName: name };
  });

  // ── 6. Fetch listings with progress ─────────────────────────────────────
  const { onComplete: onListingComplete, onPage, onDebug } = showProgress(chosenCards.length);

  const listingProgress = msg => {
    if (msg.type === 'progress')           onListingComplete(msg.card || '');
    if (msg.type === 'card_page_progress') onPage(msg.card || '', msg.fetched || 0);
    if (msg.type === 'backend_log')        onDebug(msg.text || '');
  };
  on('progress',            listingProgress);
  on('card_page_progress',  listingProgress);
  on('backend_log',         listingProgress);

  try {
    await call('fetch_listings', { tasks });
  } catch (err) {
    off('progress',           listingProgress);
    off('card_page_progress', listingProgress);
    off('backend_log',        listingProgress);
    showLogScreen('Error fetching listings.').muted(err.message);
    await waitForKey('Press Enter to go back.');
    return 'restart';
  }
  off('progress',           listingProgress);
  off('card_page_progress', listingProgress);
  off('backend_log',        listingProgress);

  return runOptimizeFlow(chosenCards, selectedSet);
}

// ── Optimize flow ──────────────────────────────────────────────────────────
async function runOptimizeFlow(chosenCards, setName) {
  // ── 1. Get filter options ────────────────────────────────────────────────
  let filterOptions = { conditions: [], sellerQuals: [] };
  let defaultFilters = {};
  try {
    const fo = await call('get_filter_options', {});
    filterOptions  = { conditions: fo.conditions || [], sellerQuals: fo.sellerQuals || [] };
    defaultFilters = { conditions: fo.defaultConditions || [], quals: fo.defaultQuals || [] };
  } catch (_) {}

  // ── 2. Initial optimized cart ────────────────────────────────────────────
  const optLog = showLogScreen('Running optimizer…');
  let optimizeResult;
  try {
    optimizeResult = await call('optimize_filtered', {
      conditions:  defaultFilters.conditions || [],
      sellerQuals: defaultFilters.quals || [],
    });
  } catch (err) {
    optLog.header('Optimizer error.');
    optLog.muted(err.message);
    await waitForKey('Press Enter to go back.');
    return 'restart';
  }

  const firstCart   = optimizeResult.firstCart   || optimizeResult.cart || [];
  const defaultCart = optimizeResult.cart         || firstCart;
  const overrides   = optimizeResult.overrides    || [];

  // ── 3. Dynamic optimizer screen ──────────────────────────────────────────
  let logHandler;
  const logHandlerFn = msg => { if (msg.type === 'backend_log' && logHandler) logHandler(msg.text); };
  on('backend_log', logHandlerFn);

  const optimizerResult = await showDynamicOptimizer(
    firstCart,
    defaultCart,
    filterOptions,
    defaultFilters,
    {
      totalCards: chosenCards.length,
      initialOverrides: overrides,
      onLog: fn => { logHandler = fn; },
    },
  );

  off('backend_log', logHandlerFn);

  if (optimizerResult.action === 'restart') return 'restart';
  if (optimizerResult.action === 'home')    return 'restart';

  const finalCart    = optimizerResult.cart;
  const cartTitle    = optimizerResult.cartTitle || 'Cart';
  const summary      = optimizerResult.summary   || buildSummary(finalCart);

  // ── 4. Confirm cart creation ─────────────────────────────────────────────
  const lines = [
    `Cart: ${cartTitle}`,
    `${summary.cards} items  •  ${summary.sellers} sellers`,
    `Subtotal: $${summary.rawCost.toFixed(2)}  •  Shipping: ~$${summary.shipping.toFixed(2)}  •  Total: ~$${summary.total.toFixed(2)}`,
    '',
    'Add these items to your TCGPlayer cart?',
  ].join('\n');

  const confirmed = await showConfirm(lines);
  if (!confirmed) return 'restart';

  // ── 5. Create cart with progress ─────────────────────────────────────────
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
    return 'restart';
  }
  off('cart_progress', cartProgressHandler);

  // ── 6. Show cart result ──────────────────────────────────────────────────
  showCartResult(cartResult);
  await waitForKey('Press Enter to return to home screen.');

  return 'restart';
}

// ── Entry ──────────────────────────────────────────────────────────────────
boot().catch(err => {
  const app = document.getElementById('app');
  app.innerHTML = `<div style="padding:16px;color:#ff8888;font-family:monospace">Fatal error: ${err.message}</div>`;
  console.error(err);
});
