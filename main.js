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
  // ── card selection helper (Save / Load / Restart / Exit support) ──────────
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
        ipc.kill();
        ui.shutdown();
        return;
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

  // 1. Boot screen first so no backend stderr bleeds through before blessed takes over
  ui.initScreen();

  // 2. Start backend
  ipc.spawnBackend();
  ipc.on('backend_log', msg => ui.muted(msg.text));

  // 3. Load theme + splash
  ui.header('Loading…');
  const theme = await ipc.call('get_theme', {});
  ui.applyTheme(theme.primary, theme.secondary, theme.accent);
  await ui.runSplash(theme.artContent, theme.primary);

  // 4. Welcome
  ui.sectionClear();
  ui.showWelcome();
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
      `Set: ${setName} — How would you like to scrape?`,
      { cols: 1 }
    );
    if (!scrapeChoice) continue;

    // Phase: card selection
    let selectedCardNames = [];
    let selectedCardIds   = [];

    let cardSelRestart = false;

    if (scrapeChoice === scrapeOpts[0]) {
      const selResult = await runCardSelection(
        cardNames, `Select cards to INCLUDE from ${setName}`, setName
      );
      if (!selResult) return;
      if (selResult.action === 'restart') {
        cardSelRestart = true;
      } else {
        selectedCardNames = selResult.selected;
        selectedCardIds   = selectedCardNames.map(n => cardData[n]);
      }

    } else if (scrapeChoice === scrapeOpts[1]) {
      const selResult = await runCardSelection(
        cardNames, `Select cards to EXCLUDE from ${setName}`, setName
      );
      if (!selResult) return;
      if (selResult.action === 'restart') {
        cardSelRestart = true;
      } else {
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
