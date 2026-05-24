'use strict';

const blessed = require('blessed');
const { spawnBackend, call, on: onEvent } = require('./ipc');

// ── screen & outer border ──────────────────────────────────────────────────

let screen, outerBox, logBox, activeWidget;
let PRIMARY = '#ffffff', SECONDARY = '#b4dcff', ACCENT = '#8cc8b4';

function rgb([r, g, b]) {
  return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`;
}

function initScreen() {
  screen = blessed.screen({
    smartCSR:    true,
    fullUnicode: true,
    title:       'TCGScraper',
    cursor:      { artificial: true, shape: 'line', blink: true, color: null },
  });

  outerBox = blessed.box({
    parent: screen,
    top: 0, left: 0, width: '100%', height: '100%',
    border: { type: 'line', fg: PRIMARY },
    style:  { border: { fg: PRIMARY } },
  });

  logBox = blessed.log({
    parent: outerBox,
    top: 0, left: 0, right: 0, bottom: 0,
    scrollable:   true,
    alwaysScroll: true,
    scrollbar: { ch: '│', track: { ch: ' ' }, style: { inverse: true } },
    tags:  true,
    style: { scrollbar: { fg: PRIMARY } },
  });

  screen.key(['C-c'], () => shutdown());
  screen.render();
}

function applyTheme(primary, secondary, accent) {
  PRIMARY   = rgb(primary);
  SECONDARY = rgb(secondary);
  ACCENT    = rgb(accent);
  if (outerBox) {
    outerBox.style.border.fg = PRIMARY;
    screen.render();
  }
}

// ── log helpers ────────────────────────────────────────────────────────────

function log(text, color) {
  const c = color || SECONDARY;
  logBox.log(`{${c}-fg}${escape(text)}{/}`);
  screen.render();
}

function header(text) {
  logBox.log(`{bold}{${PRIMARY}-fg}${escape(text)}{/}`);
  screen.render();
}

function muted(text) {
  logBox.log(`{grey-fg}${escape(text)}{/}`);
  screen.render();
}

function escape(t) {
  return String(t).replace(/\{/g, '\\{').replace(/\}/g, '\\}');
}

// ── section transitions ────────────────────────────────────────────────────

function sectionClear() {
  if (activeWidget) {
    activeWidget.destroy();
    activeWidget = null;
  }
  logBox.setContent('');
  logBox.show();
  screen.render();
}

// ── splash ─────────────────────────────────────────────────────────────────

function runSplash(artContent, primary) {
  return new Promise(resolve => {
    logBox.hide();
    const artBox = blessed.box({
      parent:  outerBox,
      top: 0, left: 0, right: 0, bottom: 0,
      tags:    false,
      content: artContent,
    });

    const steps = 24;
    let step = 0;
    const [r, g, b] = primary;
    const timer = setInterval(() => {
      const t  = Math.sin((step / steps) * Math.PI);
      const fr = Math.min(255, Math.round(r + (255 - r) * t * 0.6));
      const fg = Math.min(255, Math.round(g + (255 - g) * t * 0.6));
      const fb = Math.min(255, Math.round(b + (255 - b) * t * 0.6));
      outerBox.style.border.fg = rgb([fr, fg, fb]);
      screen.render();
      step++;
      if (step > steps) {
        clearInterval(timer);
        outerBox.style.border.fg = PRIMARY;
        artBox.destroy();
        logBox.show();
        screen.render();
        resolve();
      }
    }, 40);
  });
}

// ── screen key manager (prevents handler leak across widget calls) ─────────

function makeKeyManager() {
  const handlers = [];
  return {
    add(keys, fn) {
      screen.key(keys, fn);
      handlers.push([keys, fn]);
    },
    cleanup() {
      for (const [keys, fn] of handlers) screen.unkey(keys, fn);
      handlers.length = 0;
    },
  };
}

// ── 3-column grid select ───────────────────────────────────────────────────

function showGridSelect(items, promptText, opts = {}) {
  return new Promise(resolve => {
    sectionClear();
    header(promptText);

    const COLS = 3;
    const rows = Math.ceil(items.length / COLS);
    let curRow = 0, curCol = 0;
    const km = makeKeyManager();

    function cleanupAndResolve(value) {
      km.cleanup();
      gridBox.destroy();
      activeWidget = null;
      resolve(value);
    }

    const gridBox = blessed.box({
      parent:       outerBox,
      top: 2, left: 1, right: 1, bottom: 2,
      scrollable:   true,
      alwaysScroll: true,
      keys:         true,
      tags:         true,
      scrollbar: { ch: '│', style: { fg: PRIMARY } },
    });

    function render() {
      const w        = Math.max(30, (screen.width || 120) - 6);
      const colWidth = Math.floor(w / COLS);
      const maxText  = Math.max(4, colWidth - 2);
      const lines    = [];

      for (let r = 0; r < rows; r++) {
        let line = '';
        for (let c = 0; c < COLS; c++) {
          const idx  = r * COLS + c;
          if (idx >= items.length) {
            line += ' '.repeat(colWidth);
            continue;
          }
          const name  = items[idx];
          const isCur = (r === curRow && c === curCol);
          const cell  = name.length > maxText
            ? name.substring(0, maxText - 1) + '…'
            : name.padEnd(maxText);
          line += isCur
            ? `{white-bg}{black-fg} ${escape(cell)} {/}`
            : `{${SECONDARY}-fg} ${escape(cell)} {/}`;
        }
        lines.push(line);
      }
      gridBox.setContent(lines.join('\n'));

      const visH = Math.max(1, gridBox.height);
      const base = gridBox.childBase || 0;
      if (curRow >= base + visH) gridBox.scrollTo(curRow - visH + 1);
      else if (curRow < base)    gridBox.scrollTo(curRow);

      screen.render();
    }

    function clampCol() {
      const maxCol = Math.min(COLS - 1, items.length - 1 - curRow * COLS);
      if (curCol > maxCol) curCol = maxCol;
    }

    gridBox.key('up',       () => { if (curRow > 0) { curRow--; clampCol(); render(); } });
    gridBox.key('down',     () => { if (curRow < rows - 1) { curRow++; clampCol(); render(); } });
    gridBox.key('left',     () => { if (curCol > 0) { curCol--; render(); } });
    gridBox.key('right',    () => {
      const maxCol = Math.min(COLS - 1, items.length - 1 - curRow * COLS);
      if (curCol < maxCol) { curCol++; render(); }
    });
    gridBox.key('pageup',   () => {
      curRow = Math.max(0, curRow - Math.max(1, gridBox.height));
      clampCol(); render();
    });
    gridBox.key('pagedown', () => {
      curRow = Math.min(rows - 1, curRow + Math.max(1, gridBox.height));
      clampCol(); render();
    });
    gridBox.key(['enter', 'return'], () => {
      const idx = curRow * COLS + curCol;
      if (idx < items.length) cleanupAndResolve(items[idx]);
    });

    km.add('escape', () => cleanupAndResolve(null));
    if (opts.extraKeys) {
      for (const [key, val] of Object.entries(opts.extraKeys)) {
        km.add(key, () => cleanupAndResolve(val));
      }
    }

    gridBox.focus();
    activeWidget = gridBox;
    render();
  });
}

// ── 3-column multi-select ──────────────────────────────────────────────────

function showMultiSelect(items, promptText) {
  return new Promise(resolve => {
    sectionClear();
    header(promptText);
    header('  SPACE: toggle   ENTER: confirm   ESC: cancel');

    const COLS = 3;
    const rows = Math.ceil(items.length / COLS);
    const selected = new Set();
    let curRow = 0, curCol = 0;
    const km = makeKeyManager();

    function cleanupAndResolve(value) {
      km.cleanup();
      gridBox.destroy();
      activeWidget = null;
      resolve(value);
    }

    const gridBox = blessed.box({
      parent:       outerBox,
      top: 3, left: 1, right: 1, bottom: 2,
      scrollable:   true,
      alwaysScroll: true,
      keys:         true,
      tags:         true,
      scrollbar: { ch: '│', style: { fg: PRIMARY } },
    });

    function render() {
      const w        = Math.max(30, (screen.width || 120) - 6);
      const colWidth = Math.floor(w / COLS);
      const maxText  = Math.max(4, colWidth - 6);
      const lines    = [];

      for (let r = 0; r < rows; r++) {
        let line = '';
        for (let c = 0; c < COLS; c++) {
          const idx   = r * COLS + c;
          if (idx >= items.length) {
            line += ' '.repeat(colWidth);
            continue;
          }
          const name   = items[idx];
          const isCur  = (r === curRow && c === curCol);
          const isSel  = selected.has(idx);
          const prefix = isSel ? '[x] ' : '[ ] ';
          const cell   = name.length > maxText
            ? name.substring(0, maxText - 1) + '…'
            : name.padEnd(maxText);
          const text = escape(prefix + cell);
          if (isCur) {
            line += `{white-bg}{black-fg} ${text} {/}`;
          } else if (isSel) {
            line += `{${PRIMARY}-fg} ${text} {/}`;
          } else {
            line += `{${SECONDARY}-fg} ${text} {/}`;
          }
        }
        lines.push(line);
      }
      gridBox.setContent(lines.join('\n'));

      const visH = Math.max(1, gridBox.height);
      const base = gridBox.childBase || 0;
      if (curRow >= base + visH) gridBox.scrollTo(curRow - visH + 1);
      else if (curRow < base)    gridBox.scrollTo(curRow);

      screen.render();
    }

    function clampCol() {
      const maxCol = Math.min(COLS - 1, items.length - 1 - curRow * COLS);
      if (curCol > maxCol) curCol = maxCol;
    }

    gridBox.key('up',       () => { if (curRow > 0) { curRow--; clampCol(); render(); } });
    gridBox.key('down',     () => { if (curRow < rows - 1) { curRow++; clampCol(); render(); } });
    gridBox.key('left',     () => { if (curCol > 0) { curCol--; render(); } });
    gridBox.key('right',    () => {
      const maxCol = Math.min(COLS - 1, items.length - 1 - curRow * COLS);
      if (curCol < maxCol) { curCol++; render(); }
    });
    gridBox.key('pageup',   () => {
      curRow = Math.max(0, curRow - Math.max(1, gridBox.height));
      clampCol(); render();
    });
    gridBox.key('pagedown', () => {
      curRow = Math.min(rows - 1, curRow + Math.max(1, gridBox.height));
      clampCol(); render();
    });
    gridBox.key('space', () => {
      const idx = curRow * COLS + curCol;
      if (idx < items.length) {
        selected.has(idx) ? selected.delete(idx) : selected.add(idx);
        render();
      }
    });
    gridBox.key(['enter', 'return'], () => {
      cleanupAndResolve([...selected].sort((a, b) => a - b).map(i => items[i]));
    });
    km.add('escape', () => cleanupAndResolve([]));

    gridBox.focus();
    activeWidget = gridBox;
    render();
  });
}

// ── autocomplete (set selection) ───────────────────────────────────────────

function showAutocomplete(choices, promptText) {
  return new Promise(resolve => {
    sectionClear();
    header(promptText);
    header('  Type to filter   TAB: autocomplete   ↓/ENTER: confirm   ESC: back');

    let filtered = [...choices];
    const km = makeKeyManager();

    function cleanupAndResolve(value) {
      km.cleanup();
      inputBox.destroy();
      dropList.destroy();
      activeWidget = null;
      resolve(value);
    }

    const inputBox = blessed.textbox({
      parent: outerBox,
      top: 3, left: 1, right: 1, height: 1,
      style: { fg: PRIMARY, bg: 'black' },
      inputOnFocus: true,
    });

    const dropList = blessed.list({
      parent: outerBox,
      top: 4, left: 1, right: 1, bottom: 2,
      keys:         true,
      vi:           true,
      mouse:        true,
      scrollable:   true,
      alwaysScroll: true,
      scrollbar: { ch: '│' },
      items: filtered,
      style: {
        selected: { bg: 'white', fg: 'black', bold: true },
        item:     { fg: SECONDARY },
      },
      tags: false,
    });

    function refresh(val) {
      filtered = choices.filter(c => c.toLowerCase().includes(val.toLowerCase()));
      dropList.setItems(filtered);
      screen.render();
    }

    inputBox.on('keypress', () => setImmediate(() => refresh(inputBox.getValue())));

    inputBox.key('tab', () => {
      const choice = filtered[dropList.selected] ?? filtered[0];
      if (choice) {
        inputBox.setValue(choice);
        refresh(choice);
        inputBox.focus();
      }
    });

    inputBox.key('down', () => dropList.focus());

    inputBox.key(['enter', 'return'], () => {
      cleanupAndResolve(filtered[dropList.selected] ?? null);
    });

    dropList.key(['enter', 'return'], () => {
      cleanupAndResolve(filtered[dropList.selected] ?? null);
    });

    dropList.key('up', () => {
      if (dropList.selected === 0) inputBox.focus();
    });

    km.add('escape', () => cleanupAndResolve(null));

    inputBox.focus();
    activeWidget = inputBox;
    screen.render();
  });
}

// ── confirm dialog with highlighted arrow-key buttons ─────────────────────

function showConfirm(question) {
  return new Promise(resolve => {
    const km = makeKeyManager();
    let choice = 0; // 0 = Yes, 1 = No

    function cleanupAndResolve(value) {
      km.cleanup();
      dlg.destroy();
      activeWidget = null;
      screen.render();
      resolve(value);
    }

    const dlg = blessed.box({
      parent: outerBox,
      top: 'center', left: 'center',
      width: 64, height: 8,
      border: { type: 'line', fg: PRIMARY },
      style:  { border: { fg: PRIMARY } },
      label:  ' Confirm ',
      tags:   true,
      keys:   true,
    });

    blessed.text({
      parent: dlg,
      top: 1, left: 2, right: 2,
      content: question,
      style: { fg: SECONDARY },
    });

    const btnYes = blessed.box({
      parent: dlg,
      top: 3, left: 6, width: 14, height: 1,
      tags: true,
    });

    const btnNo = blessed.box({
      parent: dlg,
      top: 3, left: 26, width: 14, height: 1,
      tags: true,
    });

    blessed.text({
      parent: dlg,
      bottom: 0, left: 2,
      content: '←/→/TAB move   ENTER confirm   Y/N hotkeys',
      style: { fg: 'grey' },
    });

    function renderBtns() {
      if (choice === 0) {
        btnYes.setContent(`{white-bg}{black-fg}[    Yes    ]{/}`);
        btnNo.setContent(`{${SECONDARY}-fg}     No     {/}`);
      } else {
        btnYes.setContent(`{${SECONDARY}-fg}     Yes    {/}`);
        btnNo.setContent(`{white-bg}{black-fg}[    No     ]{/}`);
      }
      screen.render();
    }

    dlg.key(['left', 'right', 'tab'], () => { choice = 1 - choice; renderBtns(); });
    dlg.key(['enter', 'return'],      () => cleanupAndResolve(choice === 0));
    dlg.key('y',                      () => cleanupAndResolve(true));
    dlg.key('n',                      () => cleanupAndResolve(false));
    km.add('escape',                  () => cleanupAndResolve(false));

    dlg.focus();
    activeWidget = dlg;
    renderBtns();
  });
}

// ── progress bar (scraping) ────────────────────────────────────────────────

function showProgress(total) {
  sectionClear();
  header('Scraping card listings…');

  const barBox = blessed.progressbar({
    parent: outerBox,
    top: 3, left: 1, right: 1, height: 1,
    filled: 0,
    style: { bar: { bg: PRIMARY } },
    ch: '█',
  });

  const statusText = blessed.text({
    parent: outerBox,
    top: 5, left: 1,
    content: '',
    style: { fg: SECONDARY },
    tags: true,
  });

  let done = 0;
  return function update(cardName) {
    done++;
    const pct = Math.round((done / total) * 100);
    barBox.setProgress(pct);
    statusText.setContent(`{${SECONDARY}-fg}[${done}/${total}] ${escape(cardName)}{/}`);
    screen.render();
  };
}

// ── progress bar (cart creation) ──────────────────────────────────────────

function showCartProgress(total) {
  sectionClear();
  header('Creating cart — adding items to TCGPlayer…');
  muted('  Browser is launching. This may take a minute.');

  const barBox = blessed.progressbar({
    parent: outerBox,
    top: 4, left: 1, right: 1, height: 1,
    filled: 0,
    style: { bar: { bg: ACCENT } },
    ch: '█',
  });

  const statusText = blessed.text({
    parent: outerBox,
    top: 6, left: 1,
    content: '',
    style: { fg: SECONDARY },
    tags: true,
  });

  let done = 0;
  return function update(cardName) {
    done++;
    const pct = Math.round((done / total) * 100);
    barBox.setProgress(pct);
    statusText.setContent(`{${SECONDARY}-fg}[${done}/${total}] ${escape(cardName)}{/}`);
    screen.render();
  };
}

// ── side-by-side results comparison ───────────────────────────────────────

function showComparison(allCardData, optimizedCart) {
  sectionClear();

  const w    = Math.max(60, (screen.width || 120) - 4);
  const half = Math.floor(w / 2) - 2;
  const div  = ' │ ';

  header('RESULTS — CHEAPEST AVAILABLE vs OPTIMISED PICK');
  logBox.log(`{grey-fg}${'─'.repeat(w)}{/}`);

  logBox.log(
    `{bold}{${PRIMARY}-fg}${'CHEAPEST LISTING'.padEnd(half)}${div}OPTIMISED CART{/}`
  );
  logBox.log(`{grey-fg}${'─'.repeat(w)}{/}`);

  // build name -> optimized item lookup
  const optMap = {};
  for (const item of optimizedCart) optMap[item.card] = item;

  for (const [, data] of Object.entries(allCardData)) {
    const name     = data.card_info?.name || '?';
    const listings = data.market_listings || [];
    const opt      = optMap[name];

    const nameWidth = Math.max(10, half - 26);
    const nameTrunc = name.length > nameWidth
      ? name.substring(0, nameWidth - 1) + '…'
      : name;

    let leftStr, rightStr;

    if (listings.length) {
      const b  = listings[0];
      const sl = (b.seller || '').substring(0, 13);
      leftStr  = `${nameTrunc.padEnd(nameWidth)} $${(b.price||0).toFixed(2)}+$${(b.shipping||0).toFixed(2)} ${sl}`;
    } else {
      leftStr = `${nameTrunc.padEnd(nameWidth)} (no listings)`;
    }

    if (opt?.seller) {
      const sl = opt.seller.substring(0, 15);
      rightStr = `$${(opt.price||0).toFixed(2)}+$${(opt.shipping||0).toFixed(2)} via ${sl}`;
    } else {
      rightStr = '(not found)';
    }

    leftStr = leftStr.substring(0, half).padEnd(half);
    logBox.log(`{${SECONDARY}-fg}${escape(leftStr)}{/}${div}{${PRIMARY}-fg}${escape(rightStr)}{/}`);
  }

  logBox.log('');
  screen.render();
}

// ── cart result display ────────────────────────────────────────────────────

function showCartResult(result) {
  const { cookiePath, failedItems = [] } = result;
  logBox.log('');

  if (failedItems.length === 0) {
    logBox.log(`{bold}{${ACCENT}-fg}All items added to cart successfully!{/}`);
  } else {
    logBox.log(`{bold}{${PRIMARY}-fg}Cart done — ${failedItems.length} item(s) could not be added:{/}`);
    for (const item of failedItems) {
      logBox.log(`{grey-fg}  • ${escape(item.card)}: ${escape(item.reason)}{/}`);
    }
  }

  if (cookiePath) {
    logBox.log(`{grey-fg}Session saved to: ${escape(cookiePath)}{/}`);
  }

  logBox.log('');
  screen.render();
}

// ── wait for any keypress ──────────────────────────────────────────────────

function waitForKey(message) {
  return new Promise(resolve => {
    const hint = blessed.text({
      parent:  outerBox,
      bottom:  0, left: 2, right: 2,
      content: message,
      style:   { fg: ACCENT, bold: true },
      tags:    true,
    });
    screen.render();

    function handler() {
      screen.unkey(['enter', 'space', 'q'], handler);
      hint.destroy();
      screen.render();
      resolve();
    }
    screen.key(['enter', 'space', 'q'], handler);
  });
}

// ── shutdown ───────────────────────────────────────────────────────────────

function shutdown() {
  screen.destroy();
  process.exit(0);
}

module.exports = {
  initScreen,
  applyTheme,
  log, header, muted,
  sectionClear,
  runSplash,
  showGridSelect,
  showMultiSelect,
  showAutocomplete,
  showConfirm,
  showProgress,
  showCartProgress,
  showComparison,
  showCartResult,
  waitForKey,
  shutdown,
};
