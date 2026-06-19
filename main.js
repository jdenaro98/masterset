'use strict';

const path = require('path');
const fs   = require('fs');

const ipc = require('./ui/ipc');
const ui  = require('./ui/app');

process.on('uncaughtException', err => {
  process.stderr.write(`Uncaught: ${err.stack}\n`);
  ipc.kill();
  process.exit(1);
});

async function run() {
  // ── card selection helper (Save / Load / Restart / Home support) ──────────
  async function runCardSelection(allCardNames, promptText, setNameForFile, opts = {}) {
    const sanitized = setNameForFile.replace(/[^a-z0-9]/gi, '_');
    const defaultFile = `${sanitized}_cards.txt`;
    let initial = [];

    while (true) {
      const result = await ui.showMultiSelect(allCardNames, promptText, {
        initialSelected: initial,
        itemMeta: opts.itemMeta,
      });

      if (result.action === 'confirm') {
        return { action: 'done', selected: result.selected };
      }
      if (result.action === 'restart') {
        return { action: 'restart' };
      }
      if (result.action === 'exit') {
        return { action: 'home' };
      }
      if (result.action === 'save') {
        if (result.selected.length === 0) {
          ui.sectionClear();
          ui.muted('No cards selected — nothing to save.');
          await new Promise(r => setTimeout(r, 900));
        } else {
          const fname = await ui.showFilePicker('save', path.join(process.cwd(), defaultFile));
          if (fname) {
            ui.sectionClear();
            try {
              fs.writeFileSync(fname, result.selected.join('\n'), 'utf8');
              ui.muted(`Saved ${result.selected.length} card(s) to "${path.basename(fname)}".`);
            } catch (e) {
              ui.muted(`Save failed: ${e.message}`);
            }
            await new Promise(r => setTimeout(r, 900));
          }
        }
        initial = result.selected;
      } else if (result.action === 'load') {
        const fname = await ui.showFilePicker('open', path.join(process.cwd(), defaultFile));
        if (fname) {
          ui.sectionClear();
          try {
            const lines = fs.readFileSync(fname, 'utf8')
              .split('\n').map(l => l.trim()).filter(Boolean);
            const valid = lines.filter(n => allCardNames.includes(n));
            const skipped = lines.length - valid.length;
            if (skipped > 0) ui.muted(`${skipped} name(s) not in this set — skipped.`);
            ui.muted(`Loaded ${valid.length} card(s) from "${path.basename(fname)}".`);
            await new Promise(r => setTimeout(r, 900));
            initial = valid;
          } catch (e) {
            ui.muted(`Load failed: ${e.message}`);
            await new Promise(r => setTimeout(r, 1200));
            initial = result.selected;
          }
        } else {
          initial = result.selected;
        }
      }
    }
  }

  // ── full optimize flow (runs each time user launches from main screen) ────
  async function runOptimizeFlow() {
    // Outer loop enables "Restart" from the dynamic optimizer to re-enter
    // the game/set/card selection from scratch without returning to main screen.
    while (true) {
      ui.sectionClear();
      ui.showWelcome();
      ui.muted('\nGathering a list of TCG Games…');

      let gameData;
      try {
        gameData = await ipc.call('fetch_categories', {});
      } catch (e) {
        ui.muted(`Error fetching games: ${e.message}`);
        await new Promise(r => setTimeout(r, 1500));
        return;
      }
      const gameNames = Object.keys(gameData);

      // ── game / set / card selection loop ─────────────────────────────
      const pendingSelections = [];

      while (true) {
        const hasSelections = pendingSelections.length > 0;
        const promptText    = hasSelections
          ? 'Select a game  (D: done   R: restart)'
          : 'Select a game';
        const extraKeys     = hasSelections
          ? { d: '__done__', D: '__done__', r: '__restart__', R: '__restart__' }
          : { d: '__done__', D: '__done__' };

        ui.sectionClear();
        const gameChoice = await ui.showGridSelectWithSearch(gameNames, promptText, { extraKeys });

        if (!gameChoice || gameChoice === '__done__') break;

        if (gameChoice === '__restart__') {
          pendingSelections.length = 0;
          continue;
        }

        const gameId   = gameData[gameChoice];
        const gameName = gameChoice;

        ui.sectionClear();
        ui.header(`Game: ${gameName}`);
        ui.muted('Fetching sets…');

        let setData;
        try {
          setData = await ipc.call('fetch_sets', { gameId });
        } catch (e) {
          ui.muted(`Error fetching sets: ${e.message}`);
          continue;
        }

        const allSetNames = Object.keys(setData);

        // Run filter_sets, using disk cache when available; pass force=true to bypass.
        async function doFilterSets(force) {
          if (!force) {
            const status = await ipc.call('check_filter_cache', { gameId });
            if (status.cached) {
              ui.sectionClear();
              ui.header(`Game: ${gameName}`);
              ui.muted('Loading cached set list…');
              const res = await ipc.call('filter_sets', { gameId, sets: setData });
              return res.sets;
            }
          }
          ui.sectionClear();
          const filterHandlers = ui.showFilterProgress(allSetNames.length);
          filterProgressUpdater = filterHandlers.onComplete;
          filterDebugUpdater    = filterHandlers.onDebug;
          try {
            const res = await ipc.call('filter_sets', { gameId, sets: setData, force: !!force });
            return res.sets;
          } catch (e) {
            ui.muted(`Set probe failed, showing all: ${e.message}`);
            return setData;
          } finally {
            filterProgressUpdater = null;
            filterDebugUpdater    = null;
          }
        }

        function showHiddenCount(filtered) {
          const hidden = allSetNames.length - Object.keys(filtered).length;
          if (hidden > 0) {
            ui.muted(`  Showing ${Object.keys(filtered).length} sets (${hidden} hidden — no price data)`);
          }
        }

        let filteredSetData = await doFilterSets(false);
        showHiddenCount(filteredSetData);
        if (allSetNames.length !== Object.keys(filteredSetData).length) {
          await new Promise(r => setTimeout(r, 900));
        }

        // Set selection — refresh button re-probes and updates the cache.
        let setChoice;
        while (true) {
          ui.sectionClear();
          setChoice = await ui.showAutocomplete(
            Object.keys(filteredSetData),
            `Game: ${gameName}`,
            { showRefreshBtn: true }
          );
          if (setChoice !== '__refresh__') break;
          const confirmRefresh = await ui.showConfirm(
            'Re-fetch set list from TCGPlayer?\nThis will update cached data.'
          );
          if (!confirmRefresh) continue;
          filteredSetData = await doFilterSets(true);
          showHiddenCount(filteredSetData);
          if (allSetNames.length !== Object.keys(filteredSetData).length) {
            await new Promise(r => setTimeout(r, 900));
          }
        }
        if (!setChoice) continue;
        const setId   = filteredSetData[setChoice];
        const setName = setChoice;

        ui.sectionClear();
        ui.header(`Set: ${setName}`);
        ui.muted('Loading card list…');

        let cardData;
        try {
          const cardResult = await ipc.call('fetch_cards', { setId, gameId });
          cardData = cardResult.cards;
          if (cardResult.from_cache) {
            ui.muted('  Loaded from cache.');
          }
        } catch (e) {
          ui.muted(`Error fetching cards: ${e.message}`);
          continue;
        }
        const cardNames = Object.keys(cardData);

        if (!cardNames.length) {
          ui.muted('No cards found in this set.');
          await new Promise(r => setTimeout(r, 1500));
          continue;
        }

        const itemMeta  = cardNames.map(name => cardData[name]);
        const selResult = await runCardSelection(
          cardNames, `Select cards from ${setName}`, setName, { itemMeta }
        );
        if (selResult.action === 'home')    return;
        if (selResult.action === 'restart') continue;
        const selectedCardNames = selResult.selected;
        const selectedCardIds   = selectedCardNames.map(n => cardData[n]);

        if (!selectedCardNames.length) {
          ui.muted('No cards selected.');
          await new Promise(r => setTimeout(r, 1200));
          continue;
        }

        ui.sectionClear();
        ui.header(`Final card list for [${setName}]:`);
        selectedCardNames.forEach(n => ui.log(`  ${n}`));
        ui.log('');

        pendingSelections.push({ setName, cardNames: selectedCardNames, cardIds: selectedCardIds });

        const addMore = await ui.showConfirm('Add cards from another set to optimize together?');
        if (!addMore) break;
      }

      if (!pendingSelections.length) {
        ui.muted('No cards selected.');
        await new Promise(r => setTimeout(r, 1200));
        return;
      }

      // ── fetch all listings ──────────────────────────────────────────
      const tasks = pendingSelections.flatMap(sel =>
        sel.cardNames.map((name, i) => ({
          productId:   sel.cardIds[i].productId,
          printing:    sel.cardIds[i].printing,
          displayName: `${name} [${sel.setName}]`,
        }))
      );

      ui.sectionClear();
      const progressHandlers = ui.showProgress(tasks.length);
      progressUpdater = progressHandlers.onComplete;
      cardPageUpdater = progressHandlers.onPage;
      debugLogUpdater = progressHandlers.onDebug;

      let allCardData;
      try {
        allCardData = await ipc.call('fetch_listings', { tasks });
      } catch (e) {
        ui.muted(`Error fetching listings: ${e.message}`);
        await new Promise(r => setTimeout(r, 2000));
        return;
      } finally {
        progressUpdater = null;
        cardPageUpdater = null;
        debugLogUpdater = null;
      }

      if (process.env.DEBUG_DUMP) {
        try {
          const dump = await ipc.call('dump_listings', {});
          ui.muted(`Debug dump: ${dump.cards} card(s) written to ${dump.path}`);
          await new Promise(r => setTimeout(r, 1200));
        } catch (_) {}
      }

      // ── build first-listing cart (cheapest per card, no filter) ────
      const firstListingCart = Object.values(allCardData)
        .map(data => {
          const listings = data.market_listings || [];
          if (!listings.length) return null;
          const b = listings[0];
          return {
            card:              data.card_info.name,
            seller:            b.seller,
            seller_id:         b.seller_id,
            price:             b.price    || 0,
            shipping:          b.shipping || 0,
            shipping_deal:     b.shipping_deal,
            sku:               b.sku,
            sellerKey:         b.sellerKey,
            custom_listing_key: b.custom_listing_key,
          };
        })
        .filter(Boolean);

      // ── initial optimization (default filters) + available filter options ──
      ui.sectionClear();
      ui.muted('Optimizing cart…');

      let activeConditions = ['Near Mint', 'Lightly Played'];
      const DEFAULT_QUALS  = [];

      let defaultCart, filterOptions, defaultOverrides = [];
      try {
        let defaultResult;
        [defaultResult, filterOptions] = await Promise.all([
          ipc.call('optimize_filtered', { conditions: activeConditions, sellerQuals: DEFAULT_QUALS }),
          ipc.call('get_filter_options', {}),
        ]);
        defaultCart      = defaultResult.cart;
        defaultOverrides = defaultResult.overrides || [];
      } catch (e) {
        ui.muted(`Optimization error: ${e.message}`);
        await new Promise(r => setTimeout(r, 2000));
        return;
      }

      // ── pre-open filter fallback: widen conditions if dynamic isn't cheaper ──
      // Tries LP-only, then no-filter, before showing the screen.
      {
        const firstTotal   = ui.buildSummary(firstListingCart).total;
        const defaultTotal = ui.buildSummary(defaultCart).total;

        if (defaultTotal >= firstTotal) {
          const fallbacks = [['Lightly Played'], []];
          for (const conds of fallbacks) {
            try {
              const r = await ipc.call('optimize_filtered', { conditions: conds, sellerQuals: DEFAULT_QUALS });
              activeConditions = conds;
              defaultCart      = r.cart;
              defaultOverrides = r.overrides || [];
              if (ui.buildSummary(defaultCart).total < firstTotal) break;
            } catch (_) { break; }
          }
        }
      }

      // ── dynamic optimizer screen ────────────────────────────────────
      const dynamicResult = await ui.showDynamicOptimizer(
        firstListingCart, defaultCart, filterOptions,
        { conditions: activeConditions, quals: DEFAULT_QUALS },
        {
          totalCards: Object.keys(allCardData).length,
          initialOverrides: defaultOverrides,
          onLog: fn => { optimizerLogUpdater = fn; },
        }
      );
      optimizerLogUpdater = null;

      if (dynamicResult.action === 'home')    return;
      if (dynamicResult.action === 'restart') continue; // re-enters outer while loop

      // ── confirm & create cart ───────────────────────────────────────
      const chosenCart = dynamicResult.cart;

      const openBrowser = await ui.showConfirm(
        'Open browser and add optimized items to cart?'
      );

      if (openBrowser) {
        ui.sectionClear();
        cartProgressUpdater = ui.showCartProgress(chosenCart.length, {
          cartTitle: dynamicResult.cartTitle,
          ...dynamicResult.summary,
        });

        let cartResult = { cookiePath: null, failedItems: [] };
        try {
          cartResult = await ipc.call('create_cart', { optimizedCart: chosenCart });
        } catch (e) {
          ui.muted(`Cart error: ${e.message}`);
        } finally {
          cartProgressUpdater = null;
        }

        ui.showCartResult(cartResult);
        await ui.waitForKey(
          cartResult.cookiePath
            ? 'Cart is open in browser.  Press ENTER / SPACE / Q when you\'re done.'
            : 'Press ENTER / SPACE / Q to continue.'
        );

        try { await ipc.call('close_browser', {}); } catch (_) {}
      }

      return; // back to main screen after a completed run
    }
  }

  // ── boot ───────────────────────────────────────────────────────────────
  ui.initScreen();
  ipc.spawnBackend();
  ipc.on('backend_log', msg => {
    const handler = debugLogUpdater || filterDebugUpdater || optimizerLogUpdater;
    if (handler) handler(msg.text);
    else ui.muted(msg.text);
  });

  ui.header('Loading…');
  const theme = await ipc.call('get_theme', {});
  ui.applyTheme(theme.primary, theme.secondary, theme.accent);
  await ui.runSplash(theme.artContent, theme.primary, theme.pokemonName);

  // Register progress handlers once; closures update the active callback each run
  let progressUpdater      = null;
  let cardPageUpdater      = null;
  let cartProgressUpdater  = null;
  let debugLogUpdater      = null;
  let filterProgressUpdater = null;
  let filterDebugUpdater   = null;
  let optimizerLogUpdater  = null;
  ipc.on('progress',           msg => progressUpdater      && progressUpdater(msg.card));
  ipc.on('card_page_progress', msg => cardPageUpdater      && cardPageUpdater(msg.card, msg.fetched));
  ipc.on('cart_progress',      msg => cartProgressUpdater  && cartProgressUpdater(msg.card));
  ipc.on('probe_progress',     msg => filterProgressUpdater && filterProgressUpdater(msg.set));

  // ── main screen loop ────────────────────────────────────────────────────
  while (true) {
    const action = await ui.showMainScreen();
    if (action === 'exit') break;
    if (action === 'restart') {
      const theme = await ipc.call('get_theme', {});
      ui.applyTheme(theme.primary, theme.secondary, theme.accent);
      await ui.runSplash(theme.artContent, theme.primary, theme.pokemonName);
      continue;
    }
    await runOptimizeFlow();
  }

  ipc.kill();
  ui.shutdown();
}

run().catch(err => {
  process.stderr.write(`Fatal: ${err.stack}\n`);
  ipc.kill();
  process.exit(1);
});
