'use strict';

const { execSync, spawn } = require('child_process');
const path  = require('path');
const fs    = require('fs');

// ── launcher: open a new terminal window ──────────────────────────────────

if (!process.env.TCGSCRAPER_BORDERED) {
  const script = __filename;

  if (process.platform === 'win32') {
    try {
      execSync('where wt.exe', { stdio: 'ignore' });
      spawn('wt.exe', ['--size', '50x160', '--title', 'TCGScraper', '--', 'node', script], {
        env:      { ...process.env, TCGSCRAPER_BORDERED: '1', COLORTERM: 'truecolor', TERM: 'xterm-256color' },
        detached: true,
        stdio:    'ignore',
      }).unref();
    } catch {
      const batPath = path.join(require('os').tmpdir(), 'tcgscraper_launch.bat');
      fs.writeFileSync(batPath,
        `@echo off\r\nmode con: cols=160 lines=50\r\ntitle TCGScraper\r\nnode "${script}"\r\n`, 'utf8');
      spawn('cmd.exe', ['/c', batPath], {
        env:         { ...process.env, TCGSCRAPER_BORDERED: '1', COLORTERM: 'truecolor', TERM: 'xterm-256color' },
        detached:    true,
        stdio:       'ignore',
        windowsHide: false,
      }).unref();
    }
  } else {
    const tmp = path.join(require('os').tmpdir(), 'tcgscraper_launch.sh');
    fs.writeFileSync(tmp,
      `#!/bin/bash\nexport TCGSCRAPER_BORDERED=1\nnode "${script}"\nosascript -e 'tell application "Terminal" to close front window' 2>/dev/null || true\n`, 'utf8');
    fs.chmodSync(tmp, 0o755);
    spawn('osascript', [
      '-e', `tell application "Terminal" to do script "${tmp}"`,
      '-e', 'tell application "Terminal" to activate',
    ], { detached: true, stdio: 'ignore' }).unref();
  }

  process.exit(0);
}

// ── bordered mode: run the full TUI app ────────────────────────────────────

const ipc = require('./ui/ipc');
const ui  = require('./ui/app');

process.on('uncaughtException', err => {
  process.stderr.write(`Uncaught: ${err.stack}\n`);
  ipc.kill();
  process.exit(1);
});

async function run() {
  // ── card selection helper (Save / Load / Restart / Home support) ──────────
  async function runCardSelection(allCardNames, promptText, setNameForFile) {
    const sanitized = setNameForFile.replace(/[^a-z0-9]/gi, '_');
    const defaultFile = `${sanitized}_cards.txt`;
    let initial = [];

    while (true) {
      const result = await ui.showMultiSelect(allCardNames, promptText, { initialSelected: initial });

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
        const setNames = Object.keys(setData);

        ui.sectionClear();
        const setChoice = await ui.showAutocomplete(setNames, `Game: ${gameName}`);
        if (!setChoice) continue;
        const setId   = setData[setChoice];
        const setName = setChoice;

        ui.sectionClear();
        ui.header(`Set: ${setName}`);
        ui.muted('Fetching card list… (this may take a moment)');

        let cardData;
        try {
          cardData = await ipc.call('fetch_cards', { setId, gameId });
        } catch (e) {
          ui.muted(`Error fetching cards: ${e.message}`);
          continue;
        }
        const cardNames = Object.keys(cardData);
        const cardIds   = Object.values(cardData);

        if (!cardNames.length) {
          ui.muted('No cards found in this set.');
          await new Promise(r => setTimeout(r, 1500));
          continue;
        }

        ui.sectionClear();
        const scrapeOpts = [
          '1. Inclusive – pick specific cards',
          '2. Exclusive – whole set minus a few',
          '3. All Cards',
        ];
        const scrapeChoice = await ui.showGridSelect(
          scrapeOpts,
          `Set: ${setName} — How would you like to scrape?`,
          { cols: 1 }
        );
        if (!scrapeChoice) continue;

        let selectedCardNames = [];
        let selectedCardIds   = [];
        let cardSelRestart    = false;

        if (scrapeChoice === scrapeOpts[0]) {
          const selResult = await runCardSelection(
            cardNames, `Select cards to INCLUDE from ${setName}`, setName
          );
          if (selResult.action === 'home')    return;
          if (selResult.action === 'restart') { cardSelRestart = true; }
          else {
            selectedCardNames = selResult.selected;
            selectedCardIds   = selectedCardNames.map(n => cardData[n]);
          }

        } else if (scrapeChoice === scrapeOpts[1]) {
          const selResult = await runCardSelection(
            cardNames, `Select cards to EXCLUDE from ${setName}`, setName
          );
          if (selResult.action === 'home')    return;
          if (selResult.action === 'restart') { cardSelRestart = true; }
          else {
            const excSet = new Set(selResult.selected);
            selectedCardNames = cardNames.filter(n => !excSet.has(n));
            selectedCardIds   = selectedCardNames.map(n => cardData[n]);
          }

        } else {
          selectedCardNames = [...cardNames];
          selectedCardIds   = [...cardIds];
        }

        if (cardSelRestart) continue;

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

        const addMore = await ui.showConfirm('Add cards from another set to optimise together?');
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
          productId:   sel.cardIds[i],
          displayName: `${name} [${sel.setName}]`,
        }))
      );

      ui.sectionClear();
      const progressHandlers = ui.showProgress(tasks.length);
      progressUpdater = progressHandlers.onComplete;
      cardPageUpdater = progressHandlers.onPage;

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

      // ── initial optimisation (default filters) + available filter options ──
      ui.sectionClear();
      ui.muted('Optimising cart…');

      const DEFAULT_CONDITIONS = ['Near Mint', 'Lightly Played'];
      const DEFAULT_QUALS      = ['Verified'];

      let defaultCart, filterOptions;
      try {
        let defaultResult;
        [defaultResult, filterOptions] = await Promise.all([
          ipc.call('optimize_filtered', { conditions: DEFAULT_CONDITIONS, sellerQuals: DEFAULT_QUALS }),
          ipc.call('get_filter_options', {}),
        ]);
        defaultCart = defaultResult.cart;
      } catch (e) {
        ui.muted(`Optimisation error: ${e.message}`);
        await new Promise(r => setTimeout(r, 2000));
        return;
      }

      // ── dynamic optimizer screen ────────────────────────────────────
      const dynamicResult = await ui.showDynamicOptimizer(
        firstListingCart, defaultCart, filterOptions,
        { conditions: DEFAULT_CONDITIONS, quals: DEFAULT_QUALS }
      );

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
  ipc.on('backend_log', msg => ui.muted(msg.text));

  ui.header('Loading…');
  const theme = await ipc.call('get_theme', {});
  ui.applyTheme(theme.primary, theme.secondary, theme.accent);
  await ui.runSplash(theme.artContent, theme.primary, theme.pokemonName);

  // Register progress handlers once; closures update the active callback each run
  let progressUpdater     = null;
  let cardPageUpdater     = null;
  let cartProgressUpdater = null;
  ipc.on('progress',           msg => progressUpdater     && progressUpdater(msg.card));
  ipc.on('card_page_progress', msg => cardPageUpdater     && cardPageUpdater(msg.card, msg.fetched));
  ipc.on('cart_progress',      msg => cartProgressUpdater && cartProgressUpdater(msg.card));

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
