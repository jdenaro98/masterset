'use strict';

const blessed      = require('blessed');
const { spawn }    = require('child_process');
const fs           = require('fs');
const path         = require('path');
const { spawnBackend, call, on: onEvent } = require('./ipc');

// ── screen & outer border ──────────────────────────────────────────────────

let screen, outerBox, logBox, activeWidget;
let activeHints = [];
let progressWidgets = [];
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
  screen = blessed.screen({
    smartCSR:    true,
    fullUnicode: true,
    title:       'TCGScraper',
  });

  screen.enableMouse();

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
  for (const w of progressWidgets) { try { w.destroy(); } catch (_) {} }
  progressWidgets = [];
  logBox.setContent('');
  logBox.show();
  screen.render();
}

// ── ANSI art parser ────────────────────────────────────────────────────────

function parseArtColors(content) {
  const result = [];
  for (const rawLine of content.split('\n')) {
    const chars = [];
    let i = 0, curR = null, curG = null, curB = null;
    while (i < rawLine.length) {
      if (rawLine[i] === '\x1b' && rawLine[i + 1] === '[') {
        let j = i + 2;
        while (j < rawLine.length && rawLine[j] !== 'm') j++;
        const params = rawLine.slice(i + 2, j).split(';').map(Number);
        if (params[0] === 0 || params.length === 0) {
          curR = null; curG = null; curB = null;
        } else if (params[0] === 38 && params[1] === 2 && params.length >= 5) {
          curR = params[2]; curG = params[3]; curB = params[4];
        }
        i = j + 1;
      } else {
        chars.push({ ch: rawLine[i], r: curR, g: curG, b: curB });
        i++;
      }
    }
    result.push(chars);
  }
  return result;
}

// ── splash ─────────────────────────────────────────────────────────────────

function runSplash(artContent, primary, pokemonName) {
  return new Promise(resolve => {
    logBox.hide();

    const parsedLines = parseArtColors(artContent);
    const artH        = parsedLines.length;
    const maxArtWidth = Math.max(1, ...parsedLines.map(l => l.length));
    const boxW        = Math.max(1, (screen.cols || screen.width || 120) - 2);
    // Reserve 2 extra rows below sprite for blank line + name
    const nameRows    = pokemonName ? 2 : 0;
    const boxH        = Math.max(1, (screen.rows || screen.height || 40) - 2);
    const leftPad     = Math.max(0, Math.floor((boxW - maxArtWidth) / 2));
    const topPad      = Math.max(0, Math.floor((boxH - artH - nameRows) / 2));
    const padStr      = ' '.repeat(leftPad);

    const artBox = blessed.box({
      parent:  outerBox,
      top: 0, left: 0, right: 0, bottom: 0,
      tags:    true,
      style:   { bg: '#000000' },
    });

    // 3 shimmer pulses over ~3 seconds (~28 fps)
    const totalSteps = 90;
    const intervalMs = 35;
    const [r, g, b]  = primary;
    const bandHW     = 0.15;
    let step = 0;

    // Diagonal band sweeps TR→BL; shimmer blends each character's original color toward white
    function buildShimmerContent(t) {
      const bandPos = 1 - 2 * (step / totalSteps);
      const lines   = [];
      for (let i = 0; i < topPad; i++) lines.push('');
      for (let row = 0; row < artH; row++) {
        const parsedLine = parsedLines[row];
        let out = padStr;
        for (let col = 0; col < parsedLine.length; col++) {
          const { ch, r: origR, g: origG, b: origB } = parsedLine[col];
          if (ch === ' ') { out += ' '; continue; }
          let fr = origR !== null ? origR : 200;
          let fg = origG !== null ? origG : 200;
          let fb = origB !== null ? origB : 200;
          // Blend toward white in the shimmer band
          const diag = (col / (maxArtWidth - 1 || 1)) - (row / (artH - 1 || 1));
          const dist = Math.abs(diag - bandPos);
          if (dist < bandHW) {
            const blend = (1 - dist / bandHW) * t;
            fr = Math.min(255, Math.round(fr + (255 - fr) * blend));
            fg = Math.min(255, Math.round(fg + (255 - fg) * blend));
            fb = Math.min(255, Math.round(fb + (255 - fb) * blend));
          }
          const rh = fr.toString(16).padStart(2, '0');
          const gh = fg.toString(16).padStart(2, '0');
          const bh = fb.toString(16).padStart(2, '0');
          const esc = ch === '{' ? '\\{' : ch === '}' ? '\\}' : ch;
          out += `{#${rh}${gh}${bh}-fg}${esc}{/}`;
        }
        lines.push(out);
      }

      // Name label below the sprite
      if (pokemonName) {
        lines.push(''); // blank spacer
        const nameRow  = artH + 1;
        const nameLen  = pokemonName.length;
        const namePad  = Math.max(0, Math.floor((boxW - nameLen) / 2));
        let nameOut    = ' '.repeat(namePad);
        for (let col = 0; col < nameLen; col++) {
          const ch  = pokemonName[col];
          let fr = r, fg = g, fb = b;
          const diag = ((namePad + col) / (maxArtWidth - 1 || 1)) - (nameRow / (artH - 1 || 1));
          const dist = Math.abs(diag - bandPos);
          if (dist < bandHW) {
            const blend = (1 - dist / bandHW) * t;
            fr = Math.min(255, Math.round(fr + (255 - fr) * blend));
            fg = Math.min(255, Math.round(fg + (255 - fg) * blend));
            fb = Math.min(255, Math.round(fb + (255 - fb) * blend));
          }
          const rh  = fr.toString(16).padStart(2, '0');
          const gh  = fg.toString(16).padStart(2, '0');
          const bh  = fb.toString(16).padStart(2, '0');
          const esc = ch === '{' ? '\\{' : ch === '}' ? '\\}' : ch;
          nameOut += `{bold}{#${rh}${gh}${bh}-fg}${esc}{/}`;
        }
        lines.push(nameOut);
      }

      return lines.join('\n');
    }

    artBox.setContent(buildShimmerContent(0));
    screen.render();

    const timer = setInterval(() => {
      const envelope = Math.sin((step / totalSteps) * Math.PI);
      const pulse    = Math.abs(Math.sin((step / totalSteps) * Math.PI * 3));
      const t        = envelope * pulse;

      // Border glow
      const fr = Math.min(255, Math.round(r + (255 - r) * t * 0.85));
      const fg = Math.min(255, Math.round(g + (255 - g) * t * 0.85));
      const fb = Math.min(255, Math.round(b + (255 - b) * t * 0.85));
      outerBox.style.border.fg = rgb([fr, fg, fb]);

      // Background aura
      const bgR = Math.round(r * t * 0.25);
      const bgG = Math.round(g * t * 0.25);
      const bgB = Math.round(b * t * 0.25);
      artBox.style.bg = rgb([bgR, bgG, bgB]);

      artBox.setContent(buildShimmerContent(t));
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

    const COLS = opts.cols || 3;
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
          const idx  = c * rows + r;
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
      const maxCol = Math.min(COLS - 1, Math.floor((items.length - 1 - curRow) / rows));
      if (curCol > maxCol) curCol = maxCol;
    }

    gridBox.key('up',       () => { if (curRow > 0) { curRow--; clampCol(); render(); } });
    gridBox.key('down',     () => { if (curRow < rows - 1) { curRow++; clampCol(); render(); } });
    gridBox.key('left',     () => { if (curCol > 0) { curCol--; render(); } });
    gridBox.key('right',    () => {
      const maxCol = Math.min(COLS - 1, Math.floor((items.length - 1 - curRow) / rows));
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
      const idx = curCol * rows + curRow;
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

// ── 3-column grid select with search bar ──────────────────────────────────

function showGridSelectWithSearch(items, promptText, opts = {}) {
  return new Promise(resolve => {
    sectionClear();
    logBox.hide();
    hintWidget(promptText, 0, '#cccccc');
    hintWidget('  Type to search   TAB/SHIFT+TAB: cycle matches   ENTER: confirm   ESC: back', 1, '#888888');

    const COLS = opts.cols || 3;
    let query = '';
    let filtered = [...items];
    let listCursor = 0;
    let curRow = 0, curCol = 0;
    let destroyed = false;
    let flashTimer = null;
    const km = makeKeyManager();

    function cleanupAndResolve(value) {
      destroyed = true;
      km.cleanup();
      inputBox.destroy();
      contentBox.destroy();
      activeWidget = null;
      resolve(value);
    }

    const inputBox = blessed.textbox({
      parent: outerBox,
      top: 3, left: 1, right: 1, height: 1,
      style: { fg: PRIMARY, bg: '#000000' },
      inputOnFocus: true,
    });

    const contentBox = blessed.box({
      parent:       outerBox,
      top: 4, left: 1, right: 1, bottom: 2,
      scrollable:   true,
      alwaysScroll: true,
      keys:         true,
      tags:         true,
      scrollbar: { ch: '│', style: { fg: PRIMARY } },
    });

    function gridTotalRows() {
      return Math.ceil(items.length / COLS);
    }

    function clampCol() {
      const tRows  = gridTotalRows();
      const maxCol = Math.min(COLS - 1, Math.floor((items.length - 1 - curRow) / tRows));
      if (curCol > maxCol) curCol = maxCol;
    }

    function renderGrid() {
      const tRows    = gridTotalRows();
      const w        = Math.max(30, (screen.width || 120) - 6);
      const colWidth = Math.floor(w / COLS);
      const maxText  = Math.max(4, colWidth - 2);
      const lines    = [];

      for (let r = 0; r < tRows; r++) {
        let line = '';
        for (let c = 0; c < COLS; c++) {
          const idx  = c * tRows + r;
          if (idx >= items.length) { line += ' '.repeat(colWidth); continue; }
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
      contentBox.setContent(lines.join('\n'));

      const visH = Math.max(1, contentBox.height);
      const base  = contentBox.childBase || 0;
      if (curRow >= base + visH) contentBox.scrollTo(curRow - visH + 1);
      else if (curRow < base)    contentBox.scrollTo(curRow);

      screen.render();
    }

    function renderList() {
      if (filtered.length === 0) {
        contentBox.setContent(`{#888888-fg}  No matches{/}`);
      } else {
        const lines = filtered.map((item, idx) => {
          const isCur = idx === listCursor;
          const cell  = escape(item);
          return isCur
            ? `{#ffffff-bg}{#000000-fg} ${cell} {/}`
            : `{${SECONDARY}-fg} ${cell} {/}`;
        });
        contentBox.setContent(lines.join('\n'));
      }

      const visH = Math.max(1, contentBox.height);
      const base  = contentBox.childBase || 0;
      if (listCursor >= base + visH) contentBox.scrollTo(listCursor - visH + 1);
      else if (listCursor < base)    contentBox.scrollTo(listCursor);

      screen.render();
    }

    function render() {
      if (query.length > 0) renderList();
      else renderGrid();
    }

    function flashInvalidInput() {
      if (flashTimer) return;
      const origBg = inputBox.style.bg;
      const origFg = inputBox.style.fg;
      inputBox.style.bg = '#550000';
      inputBox.style.fg = '#ff6666';
      const warn = blessed.text({
        parent: outerBox,
        top: 2, left: 1, right: 1, height: 1,
        content: '{#ff6666-fg}  Please choose a valid option from the list{/}',
        style: { bg: '#000000' },
        tags: true,
      });
      screen.render();
      inputBox.focus();
      flashTimer = setTimeout(() => {
        flashTimer = null;
        if (destroyed) return;
        inputBox.style.bg = origBg;
        inputBox.style.fg = origFg;
        try { warn.destroy(); } catch (_) {}
        screen.render();
        inputBox.focus();
      }, 900);
    }

    function updateQuery() {
      if (destroyed) return;
      const val = inputBox.getValue();
      query = val;
      if (query) {
        filtered    = items.filter(c => c.toLowerCase().includes(query.toLowerCase()));
        listCursor  = 0;
      } else {
        filtered    = [...items];
        listCursor  = 0;
      }
      render();
    }

    inputBox.on('keypress', (ch, key) => {
      const name    = key && key.name;
      const navKeys = ['tab', 'up', 'down', 'left', 'right', 'enter', 'return', 'escape', 'pageup', 'pagedown'];
      if (navKeys.includes(name) || (key && key.full === 'S-tab')) return;
      setImmediate(updateQuery);
    });

    inputBox.key('tab', () => {
      inputBox.setValue(inputBox.getValue().replace(/\t/g, ''));
      if (query.length > 0 && filtered.length > 0) {
        listCursor = (listCursor + 1) % filtered.length;
        render();
        inputBox.focus();
      }
    });

    inputBox.key('S-tab', () => {
      inputBox.setValue(inputBox.getValue().replace(/\t/g, ''));
      if (query.length > 0 && filtered.length > 0) {
        listCursor = (listCursor - 1 + filtered.length) % filtered.length;
        render();
        inputBox.focus();
      }
    });

    inputBox.key('up', () => {
      if (query.length === 0) {
        if (curRow > 0) { curRow--; clampCol(); render(); }
      } else {
        if (listCursor > 0) { listCursor--; render(); }
      }
    });

    inputBox.key('down', () => {
      if (query.length === 0) {
        if (curRow < gridTotalRows() - 1) { curRow++; clampCol(); render(); }
      } else {
        if (listCursor < filtered.length - 1) { listCursor++; render(); }
      }
    });

    inputBox.key('left', () => {
      if (query.length === 0 && curCol > 0) { curCol--; render(); }
    });

    inputBox.key('right', () => {
      if (query.length === 0) {
        const tRows  = gridTotalRows();
        const maxCol = Math.min(COLS - 1, Math.floor((items.length - 1 - curRow) / tRows));
        if (curCol < maxCol) { curCol++; render(); }
      }
    });

    inputBox.key('pageup', () => {
      if (query.length === 0) {
        curRow = Math.max(0, curRow - Math.max(1, contentBox.height));
        clampCol(); render();
      } else {
        listCursor = Math.max(0, listCursor - Math.max(1, contentBox.height));
        render();
      }
    });

    inputBox.key('pagedown', () => {
      if (query.length === 0) {
        curRow = Math.min(gridTotalRows() - 1, curRow + Math.max(1, contentBox.height));
        clampCol(); render();
      } else {
        listCursor = Math.min(filtered.length - 1, listCursor + Math.max(1, contentBox.height));
        render();
      }
    });

    inputBox.key(['enter', 'return'], () => {
      if (query.length > 0) {
        if (filtered.length === 0) { flashInvalidInput(); return; }
        cleanupAndResolve(filtered[listCursor]);
      } else {
        const tRows = gridTotalRows();
        const idx   = curCol * tRows + curRow;
        if (idx < items.length) cleanupAndResolve(items[idx]);
      }
    });

    km.add('escape', () => cleanupAndResolve(null));

    if (opts.extraKeys) {
      for (const [key, val] of Object.entries(opts.extraKeys)) {
        inputBox.key(key, () => {
          if (query.length === 0) cleanupAndResolve(val);
        });
      }
    }

    inputBox.focus();
    activeWidget = inputBox;
    render();
  });
}

// ── 3-column multi-select ──────────────────────────────────────────────────

function showMultiSelect(items, promptText, opts = {}) {
  return new Promise(resolve => {
    sectionClear();
    logBox.hide();
    const itemMeta   = opts.itemMeta || null;
    const hasNumbers = !!(itemMeta && itemMeta.some(m => m && m.number));
    hintWidget(promptText, 0, '#cccccc');
    hintWidget(
      '  SPACE: toggle   ENTER: confirm   PgUp/PgDn: scroll   S: save   L: load   I: invert' +
      (hasNumbers ? '   Z: sort' : '') +
      '   R: restart   Q: quit',
      1, '#888888'
    );

    const COLS = 3;
    const rows = Math.ceil(items.length / COLS);
    const selected = new Set();
    let undoPrev = null;

    let sortMode = hasNumbers ? 'number' : 'alpha';

    function cardNumSortKey(origIdx) {
      const meta = itemMeta && itemMeta[origIdx];
      if (!meta || !meta.number) return Infinity;
      const n = parseInt(meta.number.split('/')[0].trim(), 10);
      return isNaN(n) ? Infinity : n;
    }

    function printingOrder(origIdx) {
      const meta = itemMeta && itemMeta[origIdx];
      const p = meta && meta.printing;
      return (!p || p === 'Normal') ? 0 : 1;
    }

    function buildSortedOrder() {
      const indices = items.map((_, i) => i);
      if (sortMode === 'number') {
        indices.sort((a, b) => {
          const na = cardNumSortKey(a), nb = cardNumSortKey(b);
          if (na !== nb) return na - nb;
          const pa = printingOrder(a), pb = printingOrder(b);
          if (pa !== pb) return pa - pb;
          return items[a].localeCompare(items[b]);
        });
      } else {
        indices.sort((a, b) => items[a].localeCompare(items[b]));
      }
      return indices;
    }

    function formatCardNum(origIdx) {
      const meta = itemMeta && itemMeta[origIdx];
      if (!meta || !meta.number) return '';
      const part = meta.number.split('/')[0].trim();
      const n = parseInt(part, 10);
      return isNaN(n) ? part : String(n);
    }

    let sortedOrder = buildSortedOrder();

    const actionBar = blessed.text({
      parent: outerBox,
      top: 2, left: 1, right: 1, height: 1,
      content: '',
      style: { bg: '#000000' },
      tags: true,
    });
    activeHints.push(actionBar);

    function renderActionBar() {
      const undoColor = undoPrev !== null ? PRIMARY : '#555555';
      const sortBtn   = hasNumbers
        ? `   {${SECONDARY}-fg}[ Z ] ${sortMode === 'number' ? 'A/Z' : '#n'}{/}`
        : '';
      actionBar.setContent(
        `  {${SECONDARY}-fg}[ A ] Select All{/}   ` +
        `{${SECONDARY}-fg}[ D ] Deselect All{/}   ` +
        `{${SECONDARY}-fg}[ I ] Invert{/}   ` +
        `{${undoColor}-fg}[ U ] Undo{/}` +
        sortBtn
      );
      screen.render();
    }

    if (opts.initialSelected) {
      for (const name of opts.initialSelected) {
        const idx = items.indexOf(name);
        if (idx >= 0) selected.add(idx);
      }
    }

    let curRow = 0, curCol = 0;
    let scrollTop = 0;
    const km = makeKeyManager();

    // outerBox border=2, hints rows 0-1, actionBar row 2, gridBox top=3, bottom=2
    function getVisH() {
      return Math.max(1, (screen.rows || screen.height || 50) - 7);
    }

    function ensureCursorVisible() {
      const visH = getVisH();
      if (curRow < scrollTop) scrollTop = curRow;
      else if (curRow >= scrollTop + visH) scrollTop = curRow - visH + 1;
    }

    function cleanupAndResolve(value) {
      km.cleanup();
      gridBox.destroy();
      activeWidget = null;
      resolve(value);
    }

    const gridBox = blessed.box({
      parent: outerBox,
      top: 3, left: 1, right: 1, bottom: 2,
      keys:   true,
      mouse:  true,
      tags:   true,
    });

    // scroll position indicator shown when content overflows
    const scrollIndicator = blessed.text({
      parent:  outerBox,
      bottom:  2, right: 2,
      height:  1,
      content: '',
      style:   { fg: '#555555' },
      tags:    false,
    });
    activeHints.push(scrollIndicator);

    function render() {
      const visH     = getVisH();
      const w        = Math.max(30, (screen.width || 120) - 6);
      const colWidth = Math.floor(w / COLS);
      const maxText  = Math.max(4, colWidth - 6);
      const lines    = [];

      const startRow = scrollTop;
      const endRow   = Math.min(rows, scrollTop + visH);

      for (let r = startRow; r < endRow; r++) {
        let line = '';
        for (let c = 0; c < COLS; c++) {
          const displayIdx = c * rows + r;
          if (displayIdx >= items.length) {
            line += ' '.repeat(colWidth);
            continue;
          }
          const origIdx = sortedOrder[displayIdx];
          const isCur   = (r === curRow && c === curCol);
          const isSel   = selected.has(origIdx);
          const prefix  = isSel ? '[x] ' : '[ ] ';
          let label     = items[origIdx];
          if (sortMode === 'number') {
            const numStr = formatCardNum(origIdx);
            if (numStr) label = `${numStr}  ${label}`;
          }
          const cell = label.length > maxText
            ? label.substring(0, maxText - 1) + '…'
            : label.padEnd(maxText);
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

      if (rows > visH) {
        scrollIndicator.setContent(`${startRow + 1}-${endRow} of ${rows}`);
      } else {
        scrollIndicator.setContent('');
      }

      screen.render();
    }

    function clampCol() {
      const maxCol = Math.min(COLS - 1, Math.floor((items.length - 1 - curRow) / rows));
      if (curCol > maxCol) curCol = maxCol;
    }

    gridBox.key('up', () => {
      if (curRow > 0) { curRow--; clampCol(); ensureCursorVisible(); render(); }
    });
    gridBox.key('down', () => {
      if (curRow < rows - 1) { curRow++; clampCol(); ensureCursorVisible(); render(); }
    });
    gridBox.key('left',  () => { if (curCol > 0) { curCol--; render(); } });
    gridBox.key('right', () => {
      const maxCol = Math.min(COLS - 1, Math.floor((items.length - 1 - curRow) / rows));
      if (curCol < maxCol) { curCol++; render(); }
    });
    gridBox.key('pageup', () => {
      const visH = getVisH();
      scrollTop = Math.max(0, scrollTop - visH);
      curRow    = scrollTop;
      clampCol(); render();
    });
    gridBox.key('pagedown', () => {
      const visH     = getVisH();
      const maxScroll = Math.max(0, rows - visH);
      scrollTop = Math.min(maxScroll, scrollTop + visH);
      curRow    = Math.min(rows - 1, scrollTop + visH - 1);
      clampCol(); render();
    });
    gridBox.on('wheelup', () => {
      const visH = getVisH();
      scrollTop = Math.max(0, scrollTop - 3);
      if (curRow >= scrollTop + visH) { curRow = scrollTop + visH - 1; clampCol(); }
      render();
    });
    gridBox.on('wheeldown', () => {
      const visH      = getVisH();
      const maxScroll = Math.max(0, rows - visH);
      scrollTop = Math.min(maxScroll, scrollTop + 3);
      if (curRow < scrollTop) { curRow = scrollTop; clampCol(); }
      render();
    });
    gridBox.key('space', () => {
      const displayIdx = curCol * rows + curRow;
      if (displayIdx < items.length) {
        const origIdx = sortedOrder[displayIdx];
        selected.has(origIdx) ? selected.delete(origIdx) : selected.add(origIdx);
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
    gridBox.key(['a', 'A'], () => {
      undoPrev = new Set(selected);
      for (let i = 0; i < items.length; i++) selected.add(i);
      renderActionBar();
      render();
    });
    gridBox.key(['d', 'D'], () => {
      undoPrev = new Set(selected);
      selected.clear();
      renderActionBar();
      render();
    });
    gridBox.key(['i', 'I'], () => {
      undoPrev = new Set(selected);
      for (let i = 0; i < items.length; i++) {
        selected.has(i) ? selected.delete(i) : selected.add(i);
      }
      renderActionBar();
      render();
    });
    gridBox.key(['u', 'U'], () => {
      if (undoPrev === null) return;
      selected.clear();
      for (const idx of undoPrev) selected.add(idx);
      undoPrev = null;
      renderActionBar();
      render();
    });
    gridBox.key(['z', 'Z'], () => {
      if (!hasNumbers) return;
      // Remember which card the cursor is on so we can restore its position.
      const currentDisplayIdx = curCol * rows + curRow;
      const currentOrigIdx = currentDisplayIdx < sortedOrder.length
        ? sortedOrder[currentDisplayIdx] : null;
      sortMode    = sortMode === 'number' ? 'alpha' : 'number';
      sortedOrder = buildSortedOrder();
      if (currentOrigIdx !== null) {
        const newDisplayIdx = sortedOrder.indexOf(currentOrigIdx);
        if (newDisplayIdx >= 0) {
          curRow = newDisplayIdx % rows;
          curCol = Math.floor(newDisplayIdx / rows);
        }
      }
      ensureCursorVisible();
      renderActionBar();
      render();
    });
    km.add('escape', () => cleanupAndResolve({ action: 'restart', selected: [] }));

    gridBox.focus();
    activeWidget = gridBox;
    renderActionBar();
    render();
  });
}

// ── autocomplete (set selection) ───────────────────────────────────────────

function showAutocomplete(choices, promptText, opts = {}) {
  return new Promise(resolve => {
    sectionClear();
    logBox.hide();
    hintWidget(promptText, 0, '#cccccc');
    if (opts.showRefreshBtn) {
      // Shorten hint to leave room for the refresh button on the right
      const h = blessed.text({
        parent: outerBox,
        top: 1, left: 1, right: 17, height: 1,
        content: '{#888888-fg}  Type to filter   ↑/↓ or TAB/SHIFT+TAB: cycle matches   ENTER: confirm   ESC: back{/}',
        style: { bg: '#000000' },
        tags: true,
      });
      activeHints.push(h);
    } else {
      hintWidget('  Type to filter   ↑/↓ or TAB/SHIFT+TAB: cycle matches   PgUp/PgDn: scroll   ENTER: confirm   ESC: back', 1, '#888888');
    }

    let filtered = [...choices];
    let destroyed = false;
    let flashTimer = null;
    const km = makeKeyManager();

    function cleanupAndResolve(value) {
      destroyed = true;
      km.cleanup();
      screen.removeListener('wheeldown', onWheelDown);
      screen.removeListener('wheelup',   onWheelUp);
      inputBox.destroy();
      dropList.destroy();
      activeWidget = null;
      resolve(value);
    }

    if (opts.showRefreshBtn) {
      const refreshBtn = blessed.box({
        parent: outerBox,
        top: 1, right: 2, width: 14, height: 1,
        content: '{#888888-fg}[ ↻ Refresh ]{/}',
        tags: true,
        mouse: true,
        clickable: true,
        style: { bg: '#000000' },
      });
      activeHints.push(refreshBtn);
      refreshBtn.on('mouseover', () => {
        refreshBtn.setContent('{#000000-fg}{#ffffff-bg}[ ↻ Refresh ]{/}');
        screen.render();
      });
      refreshBtn.on('mouseout', () => {
        refreshBtn.setContent('{#888888-fg}[ ↻ Refresh ]{/}');
        screen.render();
      });
      refreshBtn.on('click', () => cleanupAndResolve('__refresh__'));
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
      mouse:        false,
      scrollable:   true,
      alwaysScroll: true,
      scrollbar: { ch: '│', track: { ch: ' ' } },
      items: filtered,
      style: {
        selected: { bg: '#ffffff', fg: '#000000', bold: true },
        item:     { fg: SECONDARY },
        scrollbar: { fg: PRIMARY, inverse: true },
      },
      tags: false,
    });

    const onWheelDown = () => { dropList.scroll(3);  screen.render(); };
    const onWheelUp   = () => { dropList.scroll(-3); screen.render(); };
    screen.on('wheeldown', onWheelDown);
    screen.on('wheelup',   onWheelUp);

    function flashInvalidInput() {
      if (flashTimer) return;
      const origBg = inputBox.style.bg;
      const origFg = inputBox.style.fg;
      inputBox.style.bg = '#550000';
      inputBox.style.fg = '#ff6666';
      const warn = blessed.text({
        parent: outerBox,
        top: 2, left: 1, right: 1, height: 1,
        content: '{#ff6666-fg}  Please choose a valid option from the list{/}',
        style: { bg: '#000000' },
        tags: true,
      });
      screen.render();
      inputBox.focus();
      flashTimer = setTimeout(() => {
        flashTimer = null;
        if (destroyed) return;
        inputBox.style.bg = origBg;
        inputBox.style.fg = origFg;
        try { warn.destroy(); } catch (_) {}
        screen.render();
        inputBox.focus();
      }, 900);
    }

    function refresh(val) {
      filtered = choices.filter(c => c.toLowerCase().includes(val.toLowerCase()));
      dropList.setItems(filtered);
      screen.render();
    }

    inputBox.on('keypress', (ch, key) => {
      if (key && (key.name === 'tab' || key.full === 'S-tab')) return;
      setImmediate(() => refresh(inputBox.getValue()));
    });

    function cycleSelection(dir) {
      inputBox.setValue(inputBox.getValue().replace(/\t/g, ''));
      if (filtered.length === 0) { screen.render(); return; }
      const next = (dropList.selected + dir + filtered.length) % filtered.length;
      dropList.select(next);
      screen.render();
      inputBox.focus();
    }

    inputBox.key('tab',   () => cycleSelection(+1));
    inputBox.key('S-tab', () => cycleSelection(-1));

    inputBox.key('up',   () => cycleSelection(-1));
    inputBox.key('down', () => cycleSelection(+1));

    inputBox.key('pageup', () => {
      dropList.scroll(-Math.max(1, dropList.height));
      screen.render();
      inputBox.focus();
    });
    inputBox.key('pagedown', () => {
      dropList.scroll(Math.max(1, dropList.height));
      screen.render();
      inputBox.focus();
    });

    inputBox.key(['enter', 'return'], () => {
      if (filtered.length === 0) { flashInvalidInput(); return; }
      cleanupAndResolve(filtered[dropList.selected] ?? null);
    });

    dropList.key(['enter', 'return'], () => {
      if (filtered.length === 0) { flashInvalidInput(); return; }
      cleanupAndResolve(filtered[dropList.selected] ?? null);
    });

    dropList.key('up', () => {
      if (dropList.selected === 0) inputBox.focus();
    });
    dropList.key('pageup',   () => { dropList.scroll(-Math.max(1, dropList.height)); screen.render(); });
    dropList.key('pagedown', () => { dropList.scroll(Math.max(1, dropList.height));  screen.render(); });

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
      style: { fg: '#888888' },
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
  logBox.hide();

  const headerWidget = blessed.text({
    parent: outerBox,
    top: 1, left: 1, right: 1, height: 1,
    content: `{bold}{${PRIMARY}-fg}Scraping card listings…{/}`,
    style: { bg: '#000000' },
    tags: true,
  });
  progressWidgets.push(headerWidget);

  const barTrack = blessed.box({
    parent: outerBox,
    top: 3, left: 1, right: 1, height: 1,
    style: { bg: '#111111' },
  });
  progressWidgets.push(barTrack);

  const barFill = blessed.box({
    parent: barTrack,
    top: 0, left: 0, width: 0, height: 1,
    style: { bg: PRIMARY },
  });

  // Opaque background row prevents logBox content bleeding through at the status line
  const statusRowBg = blessed.box({
    parent: outerBox,
    top: 5, left: 1, right: 1, height: 1,
    style: { bg: '#000000' },
  });
  progressWidgets.push(statusRowBg);

  const statusText = blessed.text({
    parent: outerBox,
    top: 5, left: 2,
    content: '',
    style: { fg: SECONDARY },
    tags: true,
  });
  progressWidgets.push(statusText);

  const pctText = blessed.text({
    parent: outerBox,
    top: 5, right: 2,
    content: '',
    style: { fg: SECONDARY },
    tags: true,
  });
  progressWidgets.push(pctText);

  // Separator and scrollable debug log area below the progress widgets
  const debugSep = blessed.text({
    parent: outerBox,
    top: 7, left: 1, right: 1, height: 1,
    content: `{#333333-fg}${'─'.repeat(80)}{/}`,
    style: { bg: '#000000' },
    tags: true,
  });
  progressWidgets.push(debugSep);

  const debugLog = blessed.log({
    parent: outerBox,
    top: 8, left: 1, right: 1, bottom: 1,
    scrollable: true,
    alwaysScroll: true,
    tags: true,
    style: { fg: '#888888' },
  });
  progressWidgets.push(debugLog);

  let done = 0;

  function onComplete(cardName) {
    done++;
    const pct = Math.round((done / total) * 100);
    barFill.width = Math.round(Math.max(1, barTrack.width) * pct / 100);
    statusText.setContent(`{${SECONDARY}-fg}[${done}/${total}] ${escape(cardName)}{/}`);
    pctText.setContent(`{${SECONDARY}-fg}${pct}%{/}`);
    screen.render();
  }

  function onPage(cardName, count) {
    statusText.setContent(`{${SECONDARY}-fg}[${done}/${total}] ${escape(cardName)} [${count}]{/}`);
    screen.render();
  }

  function onDebug(text) {
    debugLog.log(`{#888888-fg}${escape(text)}{/}`);
    screen.render();
  }

  return { onComplete, onPage, onDebug };
}

// ── progress bar (set probing) ────────────────────────────────────────────

function showFilterProgress(total) {
  sectionClear();
  logBox.hide();

  const headerWidget = blessed.text({
    parent: outerBox,
    top: 1, left: 1, right: 1, height: 1,
    content: `{bold}{${PRIMARY}-fg}Probing sets for price data…{/}`,
    style: { bg: '#000000' },
    tags: true,
  });
  progressWidgets.push(headerWidget);

  const barTrack = blessed.box({
    parent: outerBox,
    top: 3, left: 1, right: 1, height: 1,
    style: { bg: '#111111' },
  });
  progressWidgets.push(barTrack);

  const barFill = blessed.box({
    parent: barTrack,
    top: 0, left: 0, width: 0, height: 1,
    style: { bg: PRIMARY },
  });

  const statusRowBg = blessed.box({
    parent: outerBox,
    top: 5, left: 1, right: 1, height: 1,
    style: { bg: '#000000' },
  });
  progressWidgets.push(statusRowBg);

  const statusText = blessed.text({
    parent: outerBox,
    top: 5, left: 2,
    content: '',
    style: { fg: SECONDARY },
    tags: true,
  });
  progressWidgets.push(statusText);

  const pctText = blessed.text({
    parent: outerBox,
    top: 5, right: 2,
    content: '',
    style: { fg: SECONDARY },
    tags: true,
  });
  progressWidgets.push(pctText);

  const debugSep = blessed.text({
    parent: outerBox,
    top: 7, left: 1, right: 1, height: 1,
    content: `{#333333-fg}${'─'.repeat(80)}{/}`,
    style: { bg: '#000000' },
    tags: true,
  });
  progressWidgets.push(debugSep);

  const debugLog = blessed.log({
    parent: outerBox,
    top: 8, left: 1, right: 1, bottom: 1,
    scrollable: true,
    alwaysScroll: true,
    tags: true,
    style: { fg: '#888888' },
  });
  progressWidgets.push(debugLog);

  let done = 0;

  function onComplete(setName) {
    done++;
    const pct = Math.round((done / total) * 100);
    barFill.width = Math.round(Math.max(1, barTrack.width) * pct / 100);
    statusText.setContent(`{${SECONDARY}-fg}[${done}/${total}] ${escape(setName)}{/}`);
    pctText.setContent(`{${SECONDARY}-fg}${pct}%{/}`);
    screen.render();
  }

  function onDebug(text) {
    debugLog.log(`{#888888-fg}${escape(text)}{/}`);
    screen.render();
  }

  return { onComplete, onDebug };
}

// ── progress bar (cart creation) ──────────────────────────────────────────

function showCartProgress(total, summaryInfo) {
  sectionClear();
  header('Creating cart — adding items to TCGPlayer…');
  muted('  Browser is launching. This may take a minute.');

  if (summaryInfo) {
    const divider = `{#444444-fg}${'─'.repeat(50)}{/}`;
    logBox.log('');
    logBox.log(divider);
    logBox.log(`{${SECONDARY}-fg}  Selected: {bold}{${PRIMARY}-fg}${escape(summaryInfo.cartTitle)}{/}`);
    logBox.log(
      `{${SECONDARY}-fg}  Requested: ${summaryInfo.cards}` +
      `   Sellers: ${summaryInfo.sellers}` +
      `   Subtotal: $${summaryInfo.rawCost.toFixed(2)}` +
      `   Shipping: $${summaryInfo.shipping.toFixed(2)}` +
      `   Total: $${summaryInfo.total.toFixed(2)}{/}`
    );
    logBox.log(divider);
    screen.render();
  }

  const barTrack = blessed.box({
    parent: outerBox,
    bottom: 4, left: 1, right: 1, height: 1,
    style: { bg: '#111111' },
  });
  progressWidgets.push(barTrack);

  const barFill = blessed.box({
    parent: barTrack,
    top: 0, left: 0, width: 0, height: 1,
    style: { bg: ACCENT },
  });

  // Opaque background row prevents logBox content bleeding through at the status line
  const statusRowBg = blessed.box({
    parent: outerBox,
    bottom: 2, left: 1, right: 1, height: 1,
    style: { bg: '#000000' },
  });
  progressWidgets.push(statusRowBg);

  const statusText = blessed.text({
    parent: outerBox,
    bottom: 2, left: 2,
    content: '',
    style: { fg: SECONDARY },
    tags: true,
  });
  progressWidgets.push(statusText);

  const pctText = blessed.text({
    parent: outerBox,
    bottom: 2, right: 2,
    content: '',
    style: { fg: SECONDARY },
    tags: true,
  });
  progressWidgets.push(pctText);

  let done = 0;
  return function update(cardName) {
    done++;
    const pct = Math.round((done / total) * 100);
    barFill.width = Math.round(Math.max(1, barTrack.width) * pct / 100);
    statusText.setContent(`{${SECONDARY}-fg}[${done}/${total}] ${escape(cardName)}{/}`);
    pctText.setContent(`{${SECONDARY}-fg}${pct}%{/}`);
    screen.render();
  };
}

// ── side-by-side summary comparison ───────────────────────────────────────

function showCartComparison(first, optimized) {
  sectionClear();

  const w    = Math.max(60, (screen.width || 120) - 4);
  const half = Math.floor(w / 2) - 1;
  const div  = ' │ ';

  const leftLines = [
    'FIRST LISTING',
    `  Cards requested:   ${first.cards}`,
    `  Unique sellers:    ${first.sellers}`,
    `  Subtotal:          $${first.rawCost.toFixed(2)}`,
    `  Shipping:          $${first.shipping.toFixed(2)}`,
    `  Estimated total:   $${first.total.toFixed(2)}`,
  ];
  const rightLines = [
    'OPTIMIZED CART',
    `  Cards requested:   ${optimized.cards}`,
    `  Unique sellers:    ${optimized.sellers}`,
    `  Subtotal:          $${optimized.rawCost.toFixed(2)}`,
    `  Shipping:          $${optimized.shipping.toFixed(2)}`,
    `  Estimated total:   $${optimized.total.toFixed(2)}`,
  ];

  logBox.log(`{#888888-fg}${'─'.repeat(w)}{/}`);
  for (let i = 0; i < leftLines.length; i++) {
    const l = leftLines[i].padEnd(half);
    const r = rightLines[i] || '';
    if (i === 0) {
      logBox.log(`{bold}{${SECONDARY}-fg}${escape(l)}{/}${div}{bold}{${PRIMARY}-fg}${escape(r)}{/}`);
    } else {
      logBox.log(`{${SECONDARY}-fg}${escape(l)}{/}${div}{${PRIMARY}-fg}${escape(r)}{/}`);
    }
  }
  logBox.log(`{#888888-fg}${'─'.repeat(w)}{/}`);
  logBox.log('');
  screen.render();
}

// ── cart result display ────────────────────────────────────────────────────

function showCartResult(result) {
  for (const w of progressWidgets) { try { w.destroy(); } catch (_) {} }
  progressWidgets = [];

  const { cookiePath, failedItems = [] } = result;
  logBox.log('');

  if (failedItems.length === 0) {
    logBox.log(`{bold}{${ACCENT}-fg}All items added to cart successfully!{/}`);
  } else {
    logBox.log(`{bold}{#ff9999-fg}Cart done — ${failedItems.length} item(s) could not be added:{/}`);
    for (const item of failedItems) {
      logBox.log(`{#ffbbbb-fg}  • ${escape(item.card)}: ${escape(item.reason)}{/}`);
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
      style:   { fg: '#888888' },
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
  const w         = Math.max(10, (screen.cols || screen.width || 80) - 3);
  const title     = 'Welcome to TCGScraper!';
  const pad       = Math.max(0, Math.floor((w - title.length) / 2));
  const separator = '='.repeat(w);
  header(separator);
  header(' '.repeat(pad) + title);
  header(separator);
}

// ── native OS file picker (save / open) ───────────────────────────────────

function showFilePicker(mode, defaultFilePath) {
  const dir  = defaultFilePath ? path.dirname(path.resolve(defaultFilePath)) : process.cwd();
  const base = defaultFilePath ? path.basename(defaultFilePath) : '';

  return new Promise(resolve => {
    let proc;

    try {
      if (process.platform === 'win32') {
        const dlgType  = mode === 'save' ? 'SaveFileDialog' : 'OpenFileDialog';
        const safeDir  = dir.replace(/'/g, "''");
        const safeBase = base.replace(/'/g, "''");
        const ps = [
          'Add-Type -AssemblyName System.Windows.Forms',
          `$d = New-Object System.Windows.Forms.${dlgType}`,
          `$d.Filter = 'Text files (*.txt)|*.txt|All files (*.*)|*.*'`,
          `$d.InitialDirectory = '${safeDir}'`,
          safeBase ? `$d.FileName = '${safeBase}'` : '',
          mode === 'save' ? "$d.DefaultExt = 'txt'" : '',
          mode === 'save' ? '$d.AddExtension = $true' : '',
          'if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::WriteLine($d.FileName) }',
        ].filter(Boolean).join('; ');
        proc = spawn('powershell.exe', ['-NoProfile', '-Sta', '-NonInteractive', '-Command', ps], {
          stdio: ['ignore', 'pipe', 'pipe'],
        });
      } else {
        const prompt = mode === 'save' ? 'Save cards to file:' : 'Load cards from file:';
        const args = mode === 'save'
          ? ['-e', `set r to (choose file name with prompt "${prompt}" default name "${base}")`,
             '-e', 'set p to POSIX path of r',
             '-e', 'if p does not end with ".txt" then set p to p & ".txt"',
             '-e', 'return p']
          : ['-e', `set r to (choose file of type {"public.plain-text", "txt"} with prompt "${prompt}")`,
             '-e', 'return POSIX path of r'];
        proc = spawn('osascript', args, { stdio: ['ignore', 'pipe', 'pipe'] });
      }
    } catch (_) {
      proc = null;
    }

    if (!proc) {
      const prompt = mode === 'save' ? 'Save cards to file:' : 'Load cards from file:';
      resolve(showTextInput(prompt, base));
      return;
    }

    let out = '';
    proc.stdout.on('data', d => { out += d.toString(); });
    proc.on('close', () => resolve(out.trim() || null));
    proc.on('error', () => {
      const prompt = mode === 'save' ? 'Save cards to file:' : 'Load cards from file:';
      resolve(showTextInput(prompt, base));
    });
  });
}

// ── main screen (homepage) ────────────────────────────────────────────────

function showMainScreen() {
  return new Promise(resolve => {
    sectionClear();
    logBox.hide();

    const artPath  = path.join(__dirname, '..', 'art', 'ascii', 'app', 'TCG_color.txt');
    const rawArt   = fs.readFileSync(artPath, 'utf8');
    const parsed   = parseArtColors(rawArt);

    // Keep only lines that contain at least one non-space character
    const artLines = parsed.filter(line => line.some(c => c.ch !== ' '));
    const artH     = artLines.length;
    const artW     = artLines.reduce((mx, l) => Math.max(mx, l.length), 1);

    function toTagLine(line) {
      let s = '';
      for (const { ch, r, g, b } of line) {
        if (ch === ' ') { s += ' '; continue; }
        const rh  = (r !== null ? r : 200).toString(16).padStart(2, '0');
        const gh  = (g !== null ? g : 200).toString(16).padStart(2, '0');
        const bh  = (b !== null ? b : 200).toString(16).padStart(2, '0');
        const esc = ch === '{' ? '\\{' : ch === '}' ? '\\}' : ch;
        s += `{#${rh}${gh}${bh}-fg}${esc}{/}`;
      }
      return s;
    }

    const tagLines = artLines.map(toTagLine);

    const screenH = Math.max(10, (screen.rows || screen.height || 50) - 2);
    const screenW = Math.max(20, (screen.cols || screen.width || 160) - 2);

    // Icon box: art + border (2) + 2 chars h-padding
    const boxW = Math.min(artW + 4, screenW - 4);
    const boxH = artH + 2;

    // Vertical layout: boxH + 1 gap + 1 label + 2 gap + 1 exit
    const totalH  = boxH + 5;
    const topOff  = Math.max(1, Math.floor((screenH - totalH) / 2));
    const leftOff = Math.max(1, Math.floor((screenW - boxW) / 2));

    let focused = 0; // 0 = launch icon, 1 = restart, 2 = exit
    const km    = makeKeyManager();

    function done(value) {
      km.cleanup();
      try { welcomeWidget.destroy();  } catch (_) {}
      try { iconBox.destroy();        } catch (_) {}
      try { labelWidget.destroy();    } catch (_) {}
      try { restartWidget.destroy();  } catch (_) {}
      try { exitWidget.destroy();     } catch (_) {}
      activeWidget = null;
      logBox.show();
      screen.render();
      resolve(value);
    }

    // Icon box
    const iconBox = blessed.box({
      parent:    outerBox,
      top:       topOff,
      left:      leftOff,
      width:     boxW,
      height:    boxH,
      border:    { type: 'line', fg: PRIMARY },
      style:     { border: { fg: PRIMARY }, bg: '#000000' },
      tags:      true,
      clickable: true,
      keys:      true,
    });

    // Center art horizontally inside box (inside border = boxW - 2)
    const innerW  = boxW - 2;
    const hPad    = Math.max(0, Math.floor((innerW - artW) / 2));
    const hPadStr = ' '.repeat(hPad);
    iconBox.setContent(tagLines.map(l => hPadStr + l).join('\n'));

    // Label
    const labelStr    = 'Optimize by TCG';
    const labelWidget = blessed.text({
      parent:  outerBox,
      top:     topOff + boxH + 1,
      left:    leftOff,
      width:   boxW,
      height:  1,
      tags:    true,
    });
    const lPad = Math.max(0, Math.floor((boxW - labelStr.length) / 2));
    labelWidget.setContent(`{bold}{${PRIMARY}-fg}${' '.repeat(lPad)}${escape(labelStr)}{/}`);

    // Buttons: [ Restart App ] and [ Exit ] on the same row, centered under the icon
    const restartStr  = '[ Restart App ]';
    const exitStr     = '[ Exit ]';
    const btnGap      = 3;
    const totalBtnsW  = restartStr.length + btnGap + exitStr.length;
    const btnsLeft    = leftOff + Math.max(0, Math.floor((boxW - totalBtnsW) / 2));
    const restartLeft = btnsLeft;
    const exitLeft    = btnsLeft + restartStr.length + btnGap;

    const restartWidget = blessed.box({
      parent:    outerBox,
      top:       topOff + boxH + 3,
      left:      restartLeft,
      width:     restartStr.length + 1,
      height:    1,
      tags:      true,
      clickable: true,
    });

    const exitWidget = blessed.box({
      parent:    outerBox,
      top:       topOff + boxH + 3,
      left:      exitLeft,
      width:     exitStr.length + 1,
      height:    1,
      tags:      true,
      clickable: true,
    });

    // Welcome banner — top of screen, inside border
    const welcomeText = 'Welcome to MasterSet Helper';
    const wPad = Math.max(0, Math.floor((screenW - welcomeText.length) / 2));
    const welcomeWidget = blessed.text({
      parent:  outerBox,
      top:     1,
      left:    1,
      right:   1,
      height:  1,
      content: `{bold}{${PRIMARY}-fg}${' '.repeat(wPad)}${escape(welcomeText)}{/}`,
      style:   { bg: '#000000' },
      tags:    true,
    });

    function render() {
      iconBox.style.border.fg = focused === 0 ? PRIMARY : '#333333';
      restartWidget.setContent(focused === 1
        ? `{#ffffff-bg}{#000000-fg}${escape(restartStr)}{/}`
        : `{#555555-fg}${escape(restartStr)}{/}`);
      exitWidget.setContent(focused === 2
        ? `{#ffffff-bg}{#000000-fg}${escape(exitStr)}{/}`
        : `{#555555-fg}${escape(exitStr)}{/}`);
      screen.render();
    }

    km.add(['down', 'tab'],   () => { focused = (focused + 1) % 3; render(); });
    km.add(['up', 'S-tab'],   () => { focused = (focused + 2) % 3; render(); });
    km.add(['left', 'right'], () => {
      if (focused === 1) { focused = 2; render(); }
      else if (focused === 2) { focused = 1; render(); }
    });
    km.add(['enter', 'return'], () => {
      if (focused === 0) done('launch');
      else if (focused === 1) done('restart');
      else done('exit');
    });

    iconBox.on('mouseover',       () => { focused = 0; render(); });
    restartWidget.on('mouseover', () => { focused = 1; render(); });
    exitWidget.on('mouseover',    () => { focused = 2; render(); });

    iconBox.on('click',       () => done('launch'));
    restartWidget.on('click', () => done('restart'));
    exitWidget.on('click',    () => done('exit'));

    iconBox.focus();
    activeWidget = iconBox;
    render();
  });
}

// ── cart summary helpers (also used by main.js) ───────────────────────────

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

function buildSummary(cart) {
  const sellers = new Set(cart.map(i => i.seller).filter(Boolean));
  const rawCost = cart.reduce((s, i) => s + (i.price || 0), 0);
  const shipping = calcShipping(cart);
  return { cards: cart.length, sellers: sellers.size, rawCost, shipping, total: rawCost + shipping };
}

// ── dynamic optimizer screen ──────────────────────────────────────────────
//
// Two selectable cart summaries across the top (First Listing, Dynamic
// Optimized), with Condition and Seller Qualification filter panels below
// that live-update Column 2 on every toggle.
//
// Returns Promise<{ action: 'confirm'|'restart'|'home', cart: [...] }>

function showDynamicOptimizer(firstCart, defaultCart, filterOptions, defaultFilters = {}, extra = {}) {
  return new Promise(resolve => {
    sectionClear();
    logBox.hide();

    const km = makeKeyManager();

    // ── state ──────────────────────────────────────────────────────────
    let zone         = 0;   // 0 = top (carts)   1 = bottom (filters)
    let selectedCart = 1;   // 0 = first   1 = dynamic
    let filterCol    = 0;   // 0 = conditions   1 = sellerQuals
    const filterRows = [0, 0];

    const CONDITIONS = filterOptions.conditions;
    const QUALS      = filterOptions.sellerQuals;
    const QUAL_LABELS = {
      Verified: 'Verified Seller',
      Direct:   'Direct',
      WPN:      'WPN',
    };

    // Default checked state mirrors Column 2's optimization criteria
    const defaultConds = defaultFilters.conditions || ['Near Mint', 'Lightly Played'];
    const defaultQuals = defaultFilters.quals || [];
    const condChecked = new Set(defaultConds.filter(c => CONDITIONS.includes(c)));
    const qualChecked = new Set(defaultQuals.filter(q => QUALS.includes(q)));

    const totalCards     = extra.totalCards ?? firstCart.length;
    let userCart         = defaultCart;
    let currentOverrides = extra.initialOverrides || [];
    let isCalc           = false;
    let debounceId       = null;
    let spinnerTimer     = null;
    let spinnerFrame     = 0;
    const SPINNER     = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

    const summaries = [
      { ...buildSummary(firstCart), cards: totalCards },
      buildSummary(userCart),
    ];

    // ── layout ─────────────────────────────────────────────────────────
    const CART_TOP   = 2;
    const CART_H     = 10;
    const FILTER_TOP = CART_TOP + CART_H + 2;
    const FILTER_H   = 10;
    const NOTICE_TOP = FILTER_TOP + FILTER_H;

    // ── description line ────────────────────────────────────────────────
    activeHints.push(blessed.text({
      parent:  outerBox,
      top: 0, left: 1, right: 1, height: 1,
      content: `{${SECONDARY}-fg}Select a cart option below, or customize the filters to build your own optimized cart.{/}`,
      style:   { bg: '#000000' },
      tags:    true,
    }));

    // ── hint bar ────────────────────────────────────────────────────────
    const hintWidget = blessed.text({
      parent:  outerBox,
      top: 1, left: 1, right: 1, height: 1,
      content: '',
      style:   { bg: '#000000' },
      tags:    true,
    });
    activeHints.push(hintWidget);

    // ── 2 cart boxes ───────────────────────────────────────────────────
    const CART_TITLES = ['FIRST LISTING', 'DYNAMIC OPTIMIZED'];
    const cartBoxes = [0, 1].map(i => {
      const box = blessed.box({
        parent: outerBox,
        top:    CART_TOP,
        left:   i === 0 ? 0 : '50%',
        width:  i === 0 ? '50%' : undefined,
        right:  i === 1 ? 1 : undefined,
        height: CART_H,
        border: { type: 'line' },
        style:  { border: { fg: '#333333' }, bg: '#000000' },
        tags:   true,
        keys:   true,
      });
      return box;
    });

    // ── 2 filter boxes ─────────────────────────────────────────────────
    const FILTER_LABELS = ['Filter: Condition', 'Filter: Seller Qualification'];
    const filterBoxes = [0, 1].map(i => {
      const box = blessed.box({
        parent: outerBox,
        top:    FILTER_TOP,
        left:   i === 0 ? 0     : '50%',
        width:  i === 0 ? '50%' : undefined,
        right:  i === 1 ? 1     : undefined,
        height: FILTER_H,
        border: { type: 'line' },
        label:  ` ${FILTER_LABELS[i]} `,
        style:  {
          border: { fg: '#444444' },
          bg: '#000000',
          label: { fg: SECONDARY },
        },
        tags:       true,
        scrollable: true,
        alwaysScroll: true,
        keys:       true,
      });
      return box;
    });

    // ── notice box ─────────────────────────────────────────────────────
    const noticeBox = blessed.box({
      parent: outerBox,
      top:    NOTICE_TOP,
      left:   0,
      right:  1,
      bottom: 1,
      border: { type: 'line' },
      label:  ' Notices ',
      style:  { border: { fg: '#444444' }, bg: '#000000', label: { fg: SECONDARY } },
      tags:   true,
      scrollable:   true,
      alwaysScroll: true,
    });

    // ── cleanup ────────────────────────────────────────────────────────
    function cleanupAndResolve(value) {
      km.cleanup();
      if (spinnerTimer) clearInterval(spinnerTimer);
      if (debounceId)   clearTimeout(debounceId);
      for (const b of [...cartBoxes, ...filterBoxes, noticeBox]) {
        try { b.destroy(); } catch (_) {}
      }
      activeWidget = null;
      logBox.show();
      screen.render();
      resolve(value);
    }

    // ── spinner ────────────────────────────────────────────────────────
    function startSpinner() {
      if (spinnerTimer) clearInterval(spinnerTimer);
      spinnerTimer = setInterval(() => {
        spinnerFrame = (spinnerFrame + 1) % SPINNER.length;
        renderCartBox(1);
      }, 80);
    }

    function stopSpinner() {
      if (spinnerTimer) { clearInterval(spinnerTimer); spinnerTimer = null; }
    }

    // ── debounced re-optimization ──────────────────────────────────────
    function scheduleOptimize() {
      if (debounceId) clearTimeout(debounceId);
      isCalc = true;
      startSpinner();
      debounceId = setTimeout(async () => {
        try {
          const result = await call('optimize_filtered', {
            conditions:  [...condChecked],
            sellerQuals: [...qualChecked],
          });
          userCart         = result.cart;
          currentOverrides = result.overrides || [];
          summaries[1]     = buildSummary(userCart);
        } catch (_) {
          // keep previous result on error
        } finally {
          isCalc = false;
          stopSpinner();
          renderCartBox(0);
          renderCartBox(1);
          renderNotice();
        }
      }, 300);
    }

    // ── render: single cart box ────────────────────────────────────────
    function renderCartBox(i) {
      const box        = cartBoxes[i];
      const isSelected = selectedCart === i;
      const isTopZone  = zone === 0;

      // Cheapest indicator: independent of selection/tab state; suppressed during recalc
      const cheapestIdx = (!isCalc && summaries[0].total !== summaries[1].total)
        ? (summaries[0].total < summaries[1].total ? 0 : 1)
        : -1;
      const isCheapest = cheapestIdx === i;

      // Border stays purely selection/navigation driven
      box.style.border.fg = (isTopZone && isSelected) ? PRIMARY : '#333333';

      // Inner border uses fg chars — reliable across all terminals.
      // CART_H=10 gives 8 interior rows: top bar + 6 content + bottom bar.
      // Non-cheapest boxes use empty top/bottom rows so layouts stay aligned.
      const CHEAP_GREEN = '#88cc88';
      const innerW = Math.max(4, ((typeof box.width === 'number' ? box.width : 60) - 2));
      const bar = isCheapest ? `{${CHEAP_GREEN}-fg}${'─'.repeat(innerW)}{/}` : '';

      // Wraps a content line with │ side bars, padding to fill the full width.
      // For non-cheapest boxes returns the styled text unchanged.
      function wrapLine(plainText, styledText) {
        if (!isCheapest) return styledText;
        const padLen = Math.max(0, innerW - 4 - plainText.length);
        return `{${CHEAP_GREEN}-fg}│{/} ${styledText}${' '.repeat(padLen)} {${CHEAP_GREEN}-fg}│{/}`;
      }

      if (i === 1 && isCalc) {
        const sp      = SPINNER[spinnerFrame];
        const titleStr = escape(CART_TITLES[i]);
        const spinStr  = `  ${sp} Recalculating…`;
        box.setContent([
          bar,
          wrapLine(titleStr,  `{bold}{${SECONDARY}-fg}${titleStr}{/}`),
          wrapLine('', ''),
          wrapLine(spinStr,   `{${PRIMARY}-fg}${spinStr}{/}`),
          wrapLine('', ''), wrapLine('', ''), wrapLine('', ''),
          bar,
        ].join('\n'));
      } else {
        const s        = summaries[i];
        const color    = (isTopZone && isSelected) ? PRIMARY : SECONDARY;
        const titleStr  = escape(CART_TITLES[i]);
        const cardsStr  = `  Requested: ${s.cards}`;
        const sellers   = `  Sellers:  ${s.sellers}`;
        const subtotal  = `  Subtotal: $${s.rawCost.toFixed(2)}`;
        const shipping  = `  Shipping: $${s.shipping.toFixed(2)}`;
        const total     = `  Total:    $${s.total.toFixed(2)}`;
        box.setContent([
          bar,
          wrapLine(titleStr,  `{bold}{${color}-fg}${titleStr}{/}`),
          wrapLine(cardsStr,  `{${color}-fg}${cardsStr}{/}`),
          wrapLine(sellers,   `{${color}-fg}${sellers}{/}`),
          wrapLine(subtotal,  `{${color}-fg}${subtotal}{/}`),
          wrapLine(shipping,  `{${color}-fg}${shipping}{/}`),
          wrapLine(total,     `{${color}-fg}${total}{/}`),
          bar,
        ].join('\n'));
      }
      screen.render();
    }

    // ── render: single filter box ──────────────────────────────────────
    function renderFilterBox(col) {
      const box      = filterBoxes[col];
      const items    = col === 0 ? CONDITIONS : QUALS;
      const checked  = col === 0 ? condChecked : qualChecked;
      const cursor   = filterRows[col];
      const isActive = zone === 1 && filterCol === col;

      box.style.border.fg = isActive ? SECONDARY : '#444444';

      const lines = items.map((item, idx) => {
        const label     = col === 1 ? (QUAL_LABELS[item] || item) : item;
        const isChecked = checked.has(item);
        const isCursor  = isActive && idx === cursor;
        const prefix    = isChecked ? '[x]' : '[ ]';
        const text      = `${prefix} ${escape(label)}`;
        if (isCursor)       return `{#ffffff-bg}{#000000-fg} ${text} {/}`;
        if (isChecked)      return `{${PRIMARY}-fg} ${text}{/}`;
        return `{${SECONDARY}-fg} ${text}{/}`;
      });

      box.setContent(lines.join('\n'));
      screen.render();
    }

    // ── render: hint bar ───────────────────────────────────────────────
    function renderHint() {
      const hint = zone === 0
        ? `{${PRIMARY}-fg}CARTS{/} {#888888-fg}←/→ navigate   ENTER confirm   TAB: go to filters   R restart   ESC home{/}`
        : `{${SECONDARY}-fg}FILTERS{/} {#888888-fg}←/→ columns   ↑/↓ navigate   SPACE toggle   TAB: go to carts   R restart   ESC home{/}`;
      hintWidget.setContent(`  ${hint}`);
      screen.render();
    }

    // ── render: notice box ─────────────────────────────────────────────
    function renderNotice() {
      if (!currentOverrides.length) {
        noticeBox.setContent('');
        noticeBox.style.border.fg = '#444444';
      } else {
        noticeBox.style.border.fg = '#ff9955';
        const lines = currentOverrides.map(o =>
          `{#ffaa55-fg}⚠ ${escape(o.name)}:{/} {#888888-fg}${escape(o.applied)}{/}`
        );
        noticeBox.setContent(lines.join('\n'));
      }
      screen.render();
    }

    function renderAll() {
      for (let i = 0; i < 2; i++) renderCartBox(i);
      for (let c = 0; c < 2; c++) renderFilterBox(c);
      renderNotice();
      renderHint();
    }

    // ── key bindings ───────────────────────────────────────────────────

    km.add('tab', () => {
      zone = 1 - zone;
      if (zone === 1) {
        filterBoxes[filterCol].focus();
        activeWidget = filterBoxes[filterCol];
      } else {
        cartBoxes[selectedCart].focus();
        activeWidget = cartBoxes[selectedCart];
      }
      renderAll();
    });

    km.add('left', () => {
      if (zone === 0) {
        if (selectedCart > 0) { selectedCart--; renderAll(); }
      } else {
        if (filterCol > 0) { filterCol--; renderAll(); filterBoxes[filterCol].focus(); }
      }
    });

    km.add('right', () => {
      if (zone === 0) {
        if (selectedCart < 1) { selectedCart++; renderAll(); }
      } else {
        if (filterCol < 1) { filterCol++; renderAll(); filterBoxes[filterCol].focus(); }
      }
    });

    km.add('up', () => {
      if (zone === 1 && filterRows[filterCol] > 0) {
        filterRows[filterCol]--;
        renderFilterBox(filterCol);
      }
    });

    km.add('down', () => {
      if (zone === 1) {
        const items = filterCol === 0 ? CONDITIONS : QUALS;
        if (filterRows[filterCol] < items.length - 1) {
          filterRows[filterCol]++;
          renderFilterBox(filterCol);
        }
      }
    });

    km.add('space', () => {
      if (zone !== 1) return;
      const items   = filterCol === 0 ? CONDITIONS : QUALS;
      const checked = filterCol === 0 ? condChecked : qualChecked;
      const item    = items[filterRows[filterCol]];
      if (!item) return;
      if (checked.has(item)) checked.delete(item);
      else                   checked.add(item);
      renderFilterBox(filterCol);
      scheduleOptimize();
    });

    km.add(['enter', 'return'], () => {
      if (selectedCart === 1 && isCalc) return; // block while recalculating
      const carts = [firstCart, userCart];
      cleanupAndResolve({
        action: 'confirm',
        cart: carts[selectedCart],
        cartTitle: CART_TITLES[selectedCart],
        summary: summaries[selectedCart],
      });
    });

    km.add(['r', 'R'], () => cleanupAndResolve({ action: 'restart' }));
    km.add('escape',    () => cleanupAndResolve({ action: 'home' }));

    // ── initial focus & render ─────────────────────────────────────────
    cartBoxes[selectedCart].focus();
    activeWidget = cartBoxes[selectedCart];
    renderAll();
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
  showMainScreen,
  showWelcome,
  showGridSelect,
  showGridSelectWithSearch,
  showMultiSelect,
  showAutocomplete,
  showConfirm,
  showTextInput,
  showFilePicker,
  showProgress,
  showFilterProgress,
  showCartProgress,
  showCartComparison,
  showCartResult,
  waitForKey,
  buildSummary,
  calcShipping,
  showDynamicOptimizer,
  shutdown,
};
