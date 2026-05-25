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
      spawn('wt.exe', ['--title', 'TCGScraper', '--', 'node', script], {
        env:      { ...process.env, TCGSCRAPER_BORDERED: '1' },
        detached: true,
        stdio:    'ignore',
      }).unref();
    } catch {
      spawn('cmd.exe', ['/c', 'node', script], {
        env:         { ...process.env, TCGSCRAPER_BORDERED: '1' },
        detached:    true,
        stdio:       'ignore',
        windowsHide: false,
      }).unref();
    }
  } else {
    const tmp = path.join(require('os').tmpdir(), 'tcgscraper_launch.sh');
    fs.writeFileSync(tmp,
      `#!/bin/bash\nexport TCGSCRAPER_BORDERED=1\nnode "${script}"\n`, 'utf8');
    fs.chmodSync(tmp, 0o755);
    spawn('osascript', [
      '-e', `tell application "Terminal" to do script "${tmp}; exit 0"`,
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
  // 1. Boot screen first so no backend stderr bleeds through before blessed takes over
  ui.initScreen();

  // 2. Start backend
  ipc.spawnBackend();

  // 3. Load theme + splash
  ui.header('Loading…');
  const theme = await ipc.call('get_theme', {});
  ui.applyTheme(theme.primary, theme.secondary, theme.accent);
  await ui.runSplash(theme.artContent, theme.primary);

  // 4. Welcome
  ui.sectionClear();
  ui.header('='.repeat(60));
  ui.header('  Welcome to the TCGScraper!');
  ui.header('='.repeat(60));
  ui.muted('\nGathering a list of TCG Games…');

  // 5. Fetch categories
  let gameData;
  try {
    gameData = await ipc.call('fetch_categories', {});
  } catch (e) {
    ui.muted(`Error fetching games: ${e.message}`);
    return;
  }
  const gameNames = Object.keys(gameData);

  // ── selection loop ────────────────────────────────────────────────────
  const pendingSelections = [];

  while (true) {
    // On 2nd+ iteration, show Done / Restart options
    const hasSelections = pendingSelections.length > 0;
    const promptText    = hasSelections
      ? 'Select a game  (↑↓←→ navigate   ENTER select   D: done   R: restart)'
      : 'Select a game  (↑↓←→ navigate   ENTER select   ESC: exit)';
    const extraKeys     = hasSelections
      ? { d: '__done__', D: '__done__', r: '__restart__', R: '__restart__' }
      : { d: '__done__', D: '__done__' };

    ui.sectionClear();
    const gameChoice = await ui.showGridSelect(gameNames, promptText, { extraKeys });

    if (!gameChoice || gameChoice === '__done__') break;

    if (gameChoice === '__restart__') {
      pendingSelections.length = 0;
      continue;
    }

    const gameId   = gameData[gameChoice];
    const gameName = gameChoice;

    // Phase: set select
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
    const setChoice = await ui.showAutocomplete(
      setNames,
      `Game: ${gameName}`
    );
    if (!setChoice) continue;
    const setId   = setData[setChoice];
    const setName = setChoice;

    // Phase: fetch cards
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

    // Phase: scrape mode
    ui.sectionClear();
    const scrapeOpts = [
      '1. Inclusive – pick specific cards',
      '2. Exclusive – whole set minus a few',
      '3. All Cards',
    ];
    const scrapeChoice = await ui.showGridSelect(
      scrapeOpts,
      `Set: ${setName} — How would you like to scrape?`
    );
    if (!scrapeChoice) continue;

    // Phase: card selection
    let selectedCardNames = [];
    let selectedCardIds   = [];

    if (scrapeChoice === scrapeOpts[0]) {
      ui.sectionClear();
      selectedCardNames = await ui.showMultiSelect(
        cardNames, `Select cards to INCLUDE from ${setName}`
      );
      selectedCardIds = selectedCardNames.map(n => cardData[n]);

    } else if (scrapeChoice === scrapeOpts[1]) {
      ui.sectionClear();
      const excluded = await ui.showMultiSelect(
        cardNames, `Select cards to EXCLUDE from ${setName}`
      );
      const excSet = new Set(excluded);
      selectedCardNames = cardNames.filter(n => !excSet.has(n));
      selectedCardIds   = selectedCardNames.map(n => cardData[n]);

    } else {
      selectedCardNames = [...cardNames];
      selectedCardIds   = [...cardIds];
    }

    if (!selectedCardNames.length) {
      ui.muted('No cards selected.');
      await new Promise(r => setTimeout(r, 1200));
      continue;
    }

    // Summary
    ui.sectionClear();
    ui.header(`Final card list for [${setName}]:`);
    selectedCardNames.forEach(n => ui.log(`  ${n}`));
    ui.log('');

    pendingSelections.push({ setName, cardNames: selectedCardNames, cardIds: selectedCardIds });

    const addMore = await ui.showConfirm('Add cards from another set to optimise together?');
    if (!addMore) break;
  }

  if (!pendingSelections.length) {
    ui.muted('No cards selected. Exiting.');
    await new Promise(r => setTimeout(r, 1500));
    ui.shutdown();
    return;
  }

  // ── fetch listings ────────────────────────────────────────────────────
  const tasks = pendingSelections.flatMap(sel =>
    sel.cardNames.map((name, i) => ({
      productId:   sel.cardIds[i],
      displayName: `${name} [${sel.setName}]`,
    }))
  );

  ui.sectionClear();
  const updateProgress = ui.showProgress(tasks.length);
  ipc.on('progress', msg => updateProgress(msg.card));

  let allCardData;
  try {
    allCardData = await ipc.call('fetch_listings', { tasks, maxListings: 50 });
  } catch (e) {
    ui.muted(`Error fetching listings: ${e.message}`);
    await new Promise(r => setTimeout(r, 2000));
    ui.shutdown();
    return;
  }

  // ── optimise ─────────────────────────────────────────────────────────
  ui.sectionClear();
  ui.muted('Optimising cart…');
  let optimizedCart;
  try {
    optimizedCart = await ipc.call('optimize', { allCardData });
  } catch (e) {
    ui.muted(`Optimisation error: ${e.message}`);
    await new Promise(r => setTimeout(r, 2000));
    ui.shutdown();
    return;
  }

  // ── results: side-by-side comparison ─────────────────────────────────
  ui.showComparison(allCardData, optimizedCart);
  printCart(optimizedCart, 'Optimised Cart Summary');

  const openBrowser = await ui.showConfirm(
    'Open browser and add optimised items to cart?'
  );

  if (openBrowser) {
    ui.sectionClear();
    const updateCartProgress = ui.showCartProgress(optimizedCart.length);

    // Wire cart progress before calling create_cart
    ipc.on('cart_progress', msg => updateCartProgress(msg.card));

    let cartResult = { cookiePath: null, failedItems: [] };
    try {
      cartResult = await ipc.call('create_cart', { optimizedCart });
    } catch (e) {
      ui.muted(`Cart error: ${e.message}`);
    }

    ui.showCartResult(cartResult);
    await ui.waitForKey(
      cartResult.cookiePath
        ? 'Cart is open in browser.  Press ENTER / SPACE / Q when you\'re done.'
        : 'Press ENTER / SPACE / Q to exit.'
    );

    // Tell Python to close the Playwright browser cleanly
    try { await ipc.call('close_browser', {}); } catch (_) {}
  }

  ipc.kill();
  ui.shutdown();
}

function printCart(cart, title) {
  const sellers  = new Set(cart.map(i => i.seller).filter(Boolean));
  const rawCost  = cart.reduce((s, i) => s + (i.price || 0), 0);
  const shipping = calcShipping(cart);

  ui.header(title);
  ui.log(`  Unique sellers:    ${sellers.size}`);
  ui.log(`  Raw card cost:     $${rawCost.toFixed(2)}`);
  ui.log(`  Shipping:          $${shipping.toFixed(2)}`);
  ui.log(`  Estimated total:   $${(rawCost + shipping).toFixed(2)}`);
}

function calcShipping(cart) {
  const sellers = {};
  for (const item of cart) {
    const sid = item.seller_id || item.seller;
    if (!sellers[sid]) sellers[sid] = { price: 0, ship: 0, deal: false };
    sellers[sid].price += item.price || 0;
    if ((item.shipping || 0) > sellers[sid].ship) sellers[sid].ship = item.shipping;
    if (item.shipping_deal) sellers[sid].deal = true;
  }
  let total = 0;
  for (const s of Object.values(sellers)) {
    if (!(s.deal && s.price >= 5)) total += s.ship;
  }
  return Math.round(total * 100) / 100;
}

run().catch(err => {
  process.stderr.write(`Fatal: ${err.stack}\n`);
  ipc.kill();
  process.exit(1);
});
