'use strict';

const blessed = require('blessed');
const { spawnBackend, call, on: onEvent } = require('./ipc');

// ── screen & outer border ──────────────────────────────────────────────────

let screen, outerBox, logBox, activeWidget;
let activeHints = [];
let PRIMARY = '#ffffff', SECONDARY = '#b4dcff', ACCENT = '#8cc8b4';

function rgb([r, g, b]) {
  return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`;
}

function desaturate([r, g, b], factor) {
  const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
  return [
    Math.round(gray + (r - gray) * factor),
    Math.round(gray + (g - gray) * factor),
    Math.round(gray + (b - gray) * factor),
  ];
}

function initScreen() {
  // Request a comfortable window size via VT sequence (Windows Terminal + xterm-compatible).
  // By the time runSplash is called (after async IPC), the terminal will have resized
  // and blessed will have received SIGWINCH with the updated dimensions.
  process.stdout.write('\x1b[8;50;160t');

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
    style:  { border: { fg: PRIMARY }, bg: '#000000' },
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
  const isWin = process.platform === 'win32';
  const tune  = isWin ? c => desaturate(c, 0.50) : c => c;
  PRIMARY   = rgb(tune(primary));
  SECONDARY = rgb(tune(secondary));
  ACCENT    = rgb(tune(accent));
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
  logBox.log(`{#888888-fg}${escape(text)}{/}`);
  screen.render();
}

function escape(t) {
  return String(t).replace(/\{/g, '\\{').replace(/\}/g, '\\}');
}

// ── section transitions ────────────────────────────────────────────────────

function hintWidget(text, row, hexColor) {
  const color = hexColor || '#cccccc';
  const w = blessed.text({
    parent:  outerBox,
    top: row, left: 1, right: 1, height: 1,
    content: `{${color}-fg}${escape(text)}{/}`,
    style:   { bg: '#000000' },
    tags:    true,
  });
  activeHints.push(w);
  return w;
}

function sectionClear() {
  if (activeWidget) {
    activeWidget.destroy();
    activeWidget = null;
  }
  for (const h of activeHints) h.destroy();
  activeHints = [];
  logBox.setContent('');
  logBox.show();
  screen.render();
}

// ── splash ─────────────────────────────────────────────────────────────────

function runSplash(artContent, primary) {
  return new Promise(resolve => {
    logBox.hide();

    // Vertically center the sprite in the display area
    const artLines   = artContent.split('\n');
    const boxH       = Math.max(1, (screen.rows || screen.height || 40) - 2);
    const topPad     = Math.max(0, Math.floor((boxH - artLines.length) / 2));
    const displayContent = '\n'.repeat(topPad) + artContent;

    const artBox = blessed.box({
      parent:  outerBox,
      top: 0, left: 0, right: 0, bottom: 0,
      tags:    false,
      content: displayContent,
      style:   { bg: '#000000' },
    });

    // 3 shimmer pulses over ~3 seconds (~28 fps)
    const totalSteps = 90;
    const intervalMs = 35;
    const [r, g, b]  = primary;
    let step = 0;

    const timer = setInterval(() => {
      // Fade-in/out envelope wraps 3 rapid shimmer pulses
      const envelope = Math.sin((step / totalSteps) * Math.PI);
      const pulse    = Math.abs(Math.sin((step / totalSteps) * Math.PI * 3));
      const t        = envelope * pulse;

      // Border glow
      const fr = Math.min(255, Math.round(r + (255 - r) * t * 0.85));
      const fg = Math.min(255, Math.round(g + (255 - g) * t * 0.85));
      const fb = Math.min(255, Math.round(b + (255 - b) * t * 0.85));
      outerBox.style.border.fg = rgb([fr, fg, fb]);

      // Background aura behind the sprite (tints uncolored cells of the art)
      const bgR = Math.round(r * t * 0.25);
      const bgG = Math.round(g * t * 0.25);
      const bgB = Math.round(b * t * 0.25);
      artBox.style.bg = rgb([bgR, bgG, bgB]);

      screen.render();
      step++;
      if (step > totalSteps) {
        clearInterval(timer);
        outerBox.style.border.fg = PRIMARY;
        artBox.destroy();
        logBox.show();
        screen.render();
        resolve();
      }
    }, intervalMs);
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
    logBox.hide();
    hintWidget(promptText, 0, '#cccccc');

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
            ? `{#ffffff-bg}{#000000-fg} ${escape(cell)} {/}`
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

function showMultiSelect(items, promptText, opts = {}) {
  return new Promise(resolve => {
    sectionClear();
    logBox.hide();
    hintWidget(promptText, 0, '#cccccc');
    hintWidget('  SPACE: toggle   ENTER: confirm   S: save   L: load   R: restart   Q: quit', 1, '#888888');

    const COLS = 3;
    const rows = Math.ceil(items.length / COLS);
    const selected = new Set();

    if (opts.initialSelected) {
      for (const name of opts.initialSelected) {
        const idx = items.indexOf(name);
        if (idx >= 0) selected.add(idx);
      }
    }

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
            line += `{#ffffff-bg}{#000000-fg} ${text} {/}`;
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
    const toNames = () => [...selected].sort((a, b) => a - b).map(i => items[i]);

    gridBox.key(['enter', 'return'], () => {
      cleanupAndResolve({ action: 'confirm', selected: toNames() });
    });
    gridBox.key(['s', 'S'], () => {
      cleanupAndResolve({ action: 'save', selected: toNames() });
    });
    gridBox.key(['l', 'L'], () => {
      cleanupAndResolve({ action: 'load', selected: toNames() });
    });
    gridBox.key(['r', 'R'], () => {
      cleanupAndResolve({ action: 'restart', selected: [] });
    });
    gridBox.key(['q', 'Q'], () => {
      cleanupAndResolve({ action: 'exit', selected: [] });
    });
    km.add('escape', () => cleanupAndResolve({ action: 'restart', selected: [] }));

    gridBox.focus();
    activeWidget = gridBox;
    render();
  });
}

// ── autocomplete (set selection) ───────────────────────────────────────────

function showAutocomplete(choices, promptText) {
  return new Promise(resolve => {
    sectionClear();
    logBox.hide();
    hintWidget(promptText, 0, '#cccccc');
    hintWidget('  Type to filter   TAB: autocomplete   ↓/ENTER: confirm   ESC: back', 1, '#888888');

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
      style: { fg: PRIMARY, bg: '#000000' },
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
        selected: { bg: '#ffffff', fg: '#000000', bold: true },
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
      bottom: 1, left: 2,
      content: '←/→/TAB move   ENTER confirm   Y/N hotkeys',
      style: '#888888',
    });

    function renderBtns() {
      if (choice === 0) {
        btnYes.setContent(`{#ffffff-bg}{#000000-fg}[    Yes    ]{/}`);
        btnNo.setContent(`{${SECONDARY}-fg}     No     {/}`);
      } else {
        btnYes.setContent(`{${SECONDARY}-fg}     Yes    {/}`);
        btnNo.setContent(`{#ffffff-bg}{#000000-fg}[    No     ]{/}`);
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
  logBox.log(`{#888888-fg}${'─'.repeat(w)}{/}`);

  logBox.log(
    `{bold}{${PRIMARY}-fg}${'CHEAPEST LISTING'.padEnd(half)}${div}OPTIMISED CART{/}`
  );
  logBox.log(`{#888888-fg}${'─'.repeat(w)}{/}`);

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
      logBox.log(`{#888888-fg}  • ${escape(item.card)}: ${escape(item.reason)}{/}`);
    }
  }

  if (cookiePath) {
    logBox.log(`{#888888-fg}Session saved to: ${escape(cookiePath)}{/}`);
  }

  logBox.log('');
  screen.render();
}

// ── wait for any keypress ──────────────────────────────────────────────────

function waitForKey(message) {
  return new Promise(resolve => {
    const hint = blessed.text({
      parent:  outerBox,
      bottom:  1, left: 2, right: 2,
      content: message,
      style:   { fg: '#aaaaaa', bold: true },
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

// ── simple text input modal ────────────────────────────────────────────────

function showTextInput(promptText, defaultVal = '') {
  return new Promise(resolve => {
    const km = makeKeyManager();

    function done(value) {
      km.cleanup();
      box.destroy();
      screen.render();
      resolve(value || null);
    }

    const box = blessed.box({
      parent: outerBox,
      top: 'center', left: 'center',
      width: 70, height: 8,
      border: { type: 'line', fg: PRIMARY },
      style:  { border: { fg: PRIMARY } },
      tags:   true,
    });

    blessed.text({
      parent: box,
      top: 1, left: 2, right: 2,
      content: promptText,
      style:   { fg: SECONDARY },
      tags:    false,
    });

    const inputBox = blessed.textbox({
      parent:       box,
      top: 3, left: 2, right: 2, height: 1,
      style:        { fg: PRIMARY, bg: '#000000' },
      inputOnFocus: true,
    });

    blessed.text({
      parent:  box,
      bottom:  1, left: 2,
      content: 'ENTER: confirm   ESC: cancel',
      style:   '#888888',
      tags:    false,
    });

    inputBox.key(['enter', 'return'], () => done(inputBox.getValue().trim()));
    km.add('escape', () => done(null));

    if (defaultVal) inputBox.setValue(defaultVal);
    inputBox.focus();
    screen.render();
  });
}

// ── welcome banner ────────────────────────────────────────────────────────

function showWelcome() {
  const w         = screen.cols || screen.width || 80;
  const title     = 'Welcome to TCGScraper!';
  const pad       = Math.max(0, Math.floor((w - title.length) / 2));
  const separator = '='.repeat(w);
  header(separator);
  header(' '.repeat(pad) + title);
  header(separator);
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
  showWelcome,
  showGridSelect,
  showMultiSelect,
  showAutocomplete,
  showConfirm,
  showTextInput,
  showProgress,
  showCartProgress,
  showComparison,
  showCartResult,
  waitForKey,
  shutdown,
};
