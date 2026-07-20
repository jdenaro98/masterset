'use strict';
/**
 * UI rendering — all screen components for masterset web frontend.
 */

import { call, ART_BASE, BACKEND_WS_URL } from './api.js';

// ── Theme ──────────────────────────────────────────────────────────────────
let PRIMARY   = '#ffffff';
let SECONDARY = '#b4dcff';
let ACCENT    = '#8cc8b4';

function rgbArr([r, g, b]) {
  return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`;
}

export function applyTheme(primary, secondary, accent) {
  PRIMARY   = rgbArr(primary);
  SECONDARY = rgbArr(secondary);
  ACCENT    = rgbArr(accent);
  const root = document.documentElement;
  root.style.setProperty('--primary',   PRIMARY);
  root.style.setProperty('--secondary', SECONDARY);
  root.style.setProperty('--accent',    ACCENT);
  document.getElementById('app').style.borderColor = PRIMARY;
}

// True on mice/trackpads, false on touchscreens. Hover-preview handlers are
// gated on this: on touch, a tap synthesizes mouseenter+click in the same
// gesture, and re-rendering (swapping DOM nodes) between them makes the
// browser drop the click entirely, so touch must skip straight to tapping.
const HOVER_CAPABLE = window.matchMedia('(hover: hover)').matches;

// ── Screen management ──────────────────────────────────────────────────────
const app = document.getElementById('app');
let _screen      = null;
let _keyClean    = [];
let _resizeClean = [];

// Global nav chrome (home/binder icons) interrupts the active screen by resolving
// its promise with a { __nav } sentinel. Each interruptible screen registers its
// resolver via _navScreen(); triggerScreenNav (called by app.js's NavController)
// fires it. Cleared on every screen swap so a click between screens is a no-op.
let _activeNavResolve = null;
let _keyPaused        = false;

function _navScreen(resolve) {
  _activeNavResolve = target => { _activeNavResolve = null; resolve({ __nav: target }); };
}

// Called by app.js when a nav icon is clicked. Returns true if a screen was
// listening (and has now been asked to navigate), false if none is active.
export function triggerScreenNav(target) {
  const fn = _activeNavResolve;
  if (!fn) return false;
  fn(target);
  return true;
}

// Temporarily detach the active screen's key handlers while a modal (e.g. the nav
// guard confirm) is open, so the screen underneath doesn't also act on Enter/arrows.
export function pauseScreenKeys() {
  if (_keyPaused) return;
  _keyClean.forEach(fn => document.removeEventListener('keydown', fn));
  _keyPaused = true;
}
export function resumeScreenKeys() {
  if (!_keyPaused) return;
  _keyClean.forEach(fn => document.addEventListener('keydown', fn));
  _keyPaused = false;
}

function _clearScreen() {
  _keyClean.forEach(fn => document.removeEventListener('keydown', fn));
  _keyClean = [];
  _resizeClean.forEach(fn => window.removeEventListener('resize', fn));
  _resizeClean = [];
  _activeNavResolve = null;
  _keyPaused = false;
  if (_screen) { _screen.remove(); _screen = null; }
}

function _makeScreen() {
  _clearScreen();
  const div = document.createElement('div');
  div.className = 'screen';
  app.appendChild(div);
  _screen = div;
  return div;
}

function _onKey(fn) {
  document.addEventListener('keydown', fn);
  _keyClean.push(fn);
}

// Debounced resize hook so grids can re-flow their column count responsively.
function _onResize(fn) {
  let t = null;
  const handler = () => { clearTimeout(t); t = setTimeout(fn, 100); };
  window.addEventListener('resize', handler);
  _resizeClean.push(handler);
}

// Column count for responsive item grids: 1 col on narrow/mobile widths,
// 2 on tablet widths, up to `max` (the grid's own ceiling) on desktop.
function _responsiveCols(max = 3) {
  const w = window.innerWidth;
  let cols = 3;
  if (w < 640) cols = 1;
  else if (w < 960) cols = 2;
  return Math.max(1, Math.min(cols, max));
}

// ── ANSI art parser ────────────────────────────────────────────────────────
export function parseArtColors(content) {
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

// ── Canvas art helpers ─────────────────────────────────────────────────────
function _measureCanvas() {
  const tmp = document.createElement('canvas');
  const ctx = tmp.getContext('2d');
  const FONT = '14px "Fira Code", "Cascadia Code", "Courier New", monospace';
  ctx.font = FONT;
  const m = ctx.measureText('W');
  return { font: FONT, charW: m.width, charH: 18, baseline: 4 };
}
const CHAR_METRICS = _measureCanvas();

function _makeArtCanvas(parsedLines) {
  const artW = Math.max(...parsedLines.map(l => l.length), 1);
  const artH = parsedLines.length;
  const cv = document.createElement('canvas');
  cv.width  = Math.ceil(artW * CHAR_METRICS.charW);
  cv.height = artH * CHAR_METRICS.charH;
  cv.style.maxWidth  = '100%';
  cv.style.imageRendering = 'pixelated';
  return cv;
}

function _drawArt(cv, parsedLines, shimmerT = 0, bandPos = 0) {
  const ctx  = cv.getContext('2d');
  const artW = Math.max(...parsedLines.map(l => l.length), 1);
  const artH = parsedLines.length;
  const { font, charW, charH, baseline } = CHAR_METRICS;
  const bandHW = 0.15;
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.font = font;
  for (let row = 0; row < artH; row++) {
    const line = parsedLines[row];
    for (let col = 0; col < line.length; col++) {
      const { ch, r: origR, g: origG, b: origB } = line[col];
      if (ch === ' ' || origR === null) continue;
      let fr = origR, fg = origG, fb = origB;
      if (shimmerT > 0) {
        const diag = (col / (artW - 1 || 1)) - (row / (artH - 1 || 1));
        const dist = Math.abs(diag - bandPos);
        if (dist < bandHW) {
          const blend = (1 - dist / bandHW) * shimmerT;
          fr = Math.min(255, Math.round(fr + (255 - fr) * blend));
          fg = Math.min(255, Math.round(fg + (255 - fg) * blend));
          fb = Math.min(255, Math.round(fb + (255 - fb) * blend));
        }
      }
      ctx.fillStyle = `rgb(${fr},${fg},${fb})`;
      ctx.fillText(ch, col * charW, (row + 1) * charH - baseline);
    }
  }
}

// ── Splash screen ──────────────────────────────────────────────────────────
export function runSplash(artContent, primary, pokemonName) {
  return new Promise(resolve => {
    const parsedLines = parseArtColors(artContent).filter(l => l.some(c => c.ch !== ' '));
    const [r, g, b]  = primary;

    const screen = _makeScreen();
    screen.className = 'screen splash';

    const cv = _makeArtCanvas(parsedLines);
    screen.appendChild(cv);

    const nameEl = document.createElement('div');
    nameEl.className = 'splash-name';
    nameEl.textContent = pokemonName;
    screen.appendChild(nameEl);

    const hint = document.createElement('div');
    hint.className = 'hint';
    hint.textContent = 'click or press any key to continue';
    screen.appendChild(hint);

    const totalSteps = 90;
    let step = 0, finished = false;

    function finish() {
      if (finished) return;
      finished = true;
      resolve();
    }

    function frame() {
      if (finished) return;
      const bandPos  = 1 - 2 * (step / totalSteps);
      const envelope = Math.sin((step / totalSteps) * Math.PI);
      const pulse    = Math.abs(Math.sin((step / totalSteps) * Math.PI * 3));
      const t        = envelope * pulse;

      _drawArt(cv, parsedLines, t, bandPos);

      const nr = Math.min(255, Math.round(r + (255 - r) * t * 0.85));
      const ng = Math.min(255, Math.round(g + (255 - g) * t * 0.85));
      const nb = Math.min(255, Math.round(b + (255 - b) * t * 0.85));
      nameEl.style.color = `rgb(${nr},${ng},${nb})`;

      step++;
      if (step <= totalSteps) requestAnimationFrame(frame);
      else finish();
    }

    requestAnimationFrame(frame);
    screen.addEventListener('click', finish, { once: true });
    const kh = () => finish();
    document.addEventListener('keydown', kh, { once: true });
    _keyClean.push(kh);
  });
}

// ── Main screen ────────────────────────────────────────────────────────────
export async function showMainScreen() {
  // Fetch the TCG logo art from the backend.
  let parsedLogo = null;
  try {
    const res  = await fetch(`${ART_BASE}/ascii/app/TCG_color.txt`);
    const text = await res.text();
    parsedLogo = parseArtColors(text).filter(l => l.some(c => c.ch !== ' '));
  } catch (_) {}

  return new Promise(resolve => {
    const screen = _makeScreen();
    screen.className = 'screen main-screen';
    _navScreen(resolve);

    const welcome = document.createElement('div');
    welcome.className = 'main-welcome';
    welcome.textContent = 'Welcome to masterset!';
    screen.appendChild(welcome);

    // Logo box
    const logoBox = document.createElement('div');
    logoBox.className = 'main-logo-box focused';
    if (parsedLogo) {
      const cv = _makeArtCanvas(parsedLogo);
      _drawArt(cv, parsedLogo);
      logoBox.appendChild(cv);
    } else {
      logoBox.textContent = 'masterset';
      logoBox.style.cssText = 'padding:12px 24px;font-size:24px;font-weight:bold;';
    }
    screen.appendChild(logoBox);

    const label = document.createElement('div');
    label.className = 'main-label';
    label.textContent = 'Optimize by TCG';
    screen.appendChild(label);

    const btns = document.createElement('div');
    btns.className = 'main-btns';

    const restartBtn = document.createElement('button');
    restartBtn.className = 'main-btn';
    restartBtn.textContent = '[ Restart App ]';

    btns.appendChild(restartBtn);
    screen.appendChild(btns);

    // Show BMC link on main screen
    const bmc = document.createElement('div');
    bmc.className = 'bmc-bar show';
    bmc.innerHTML = '<span class="bmc-label">Support masterset →</span> <a href="https://buymeacoffee.com/jdenaro" target="_blank" rel="noopener">☕ Buy me a coffee</a>';
    screen.appendChild(bmc);

    // Focus tracking: 0=logo, 1=restart
    let focused = 0;
    const focusEls = [logoBox, restartBtn];

    function render() {
      focusEls.forEach((el, i) => el.classList.toggle('focused', i === focused));
    }

    function done(action) { resolve(action); }

    logoBox.addEventListener('click',    () => done('launch'));
    restartBtn.addEventListener('click', () => done('restart'));

    _onKey(e => {
      if (e.key === 'ArrowDown' || e.key === 'Tab' || e.key === 'ArrowUp') {
        e.preventDefault();
        focused = focused === 0 ? 1 : 0; render();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (focused === 0) done('launch');
        else done('restart');
      }
    });

    render();
  });
}

// ── Grid select with search (game selection) ───────────────────────────────
export function showGridSelectWithSearch(items, promptText, opts = {}) {
  return new Promise(resolve => {
    const screen = _makeScreen();
    screen.className = 'screen';
    _navScreen(resolve);

    const prompt = document.createElement('div');
    prompt.className = 'prompt';
    prompt.textContent = promptText;
    screen.appendChild(prompt);

    const hint = document.createElement('div');
    hint.className = 'hint';
    hint.textContent = 'type to search  •  arrows to navigate  •  enter to confirm  •  esc to go back';
    screen.appendChild(hint);

    const searchWrap = document.createElement('div');
    searchWrap.className = 'search-wrap';
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Search…';
    input.autocomplete = 'off';
    input.spellcheck = false;
    searchWrap.appendChild(input);
    screen.appendChild(searchWrap);

    const grid = document.createElement('div');
    screen.appendChild(grid);

    const actionHint = document.createElement('div');
    actionHint.className = 'hint';
    screen.appendChild(actionHint);

    let query = '';
    let filtered = [...items];
    let focusIdx = 0;  // index in the visible list/grid
    let listMode = false;

    function getVisible() { return listMode ? filtered : items; }

    function updateActionHint() {
      const extra = opts.extraKeys
        ? '  •  ' + Object.entries(opts.extraKeys)
            .map(([k, v]) => `${k.toUpperCase()}: ${v === '__done__' ? 'done' : v === '__restart__' ? 'restart' : v}`)
            .join('  ')
        : '';
      actionHint.textContent = extra;
    }

    function render() {
      const visible = getVisible();
      focusIdx = Math.min(focusIdx, Math.max(0, visible.length - 1));

      if (listMode || query) {
        grid.className = 'list-box';
        grid.innerHTML = '';
        filtered.forEach((item, i) => {
          const el = document.createElement('div');
          el.className = 'list-item' + (i === focusIdx ? ' focused' : '');
          el.textContent = item;
          el.addEventListener('click', () => { focusIdx = i; resolve(filtered[i]); });
          el.addEventListener('mouseenter', () => { if (!HOVER_CAPABLE) return; focusIdx = i; render(); });
          grid.appendChild(el);
        });
        // Scroll focused into view
        const focusedEl = grid.children[focusIdx];
        if (focusedEl) focusedEl.scrollIntoView({ block: 'nearest' });
      } else {
        grid.className = 'grid-box';
        grid.innerHTML = '';
        const COLS = opts.cols || 3;
        const rows = Math.ceil(items.length / COLS);
        // Items are laid out column-first (same as TUI)
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < COLS; c++) {
            const idx = c * rows + r;
            if (idx >= items.length) {
              const empty = document.createElement('div');
              grid.appendChild(empty);
              continue;
            }
            // Compute linear focus index (row-major order for display)
            const linearIdx = c * rows + r;
            const el = document.createElement('div');
            el.className = 'grid-item' + (linearIdx === focusIdx ? ' focused' : '');
            el.textContent = items[idx];
            const capturedLinear = linearIdx;
            const capturedItem   = items[idx];
            el.addEventListener('click', () => resolve(capturedItem));
            el.addEventListener('mouseenter', () => { if (!HOVER_CAPABLE) return; focusIdx = capturedLinear; render(); });
            grid.appendChild(el);
          }
        }
        // Scroll focused into view
        const focusedEl = grid.children[focusIdx];
        if (focusedEl) focusedEl.scrollIntoView({ block: 'nearest' });
      }
      updateActionHint();
    }

    input.addEventListener('input', () => {
      query    = input.value;
      listMode = query.length > 0;
      filtered = query ? items.filter(c => c.toLowerCase().includes(query.toLowerCase())) : [...items];
      focusIdx = 0;
      render();
    });

    function getSelectedItem() {
      const visible = getVisible();
      return visible[focusIdx] ?? null;
    }

    _onKey(e => {
      const COLS = opts.cols || 3;
      const rows = Math.ceil(items.length / COLS);
      const visible = getVisible();

      if (e.key === 'Escape') { e.preventDefault(); resolve(null); return; }
      if (e.key === 'Enter') {
        e.preventDefault();
        const item = getSelectedItem();
        if (item) resolve(item);
        return;
      }

      if (opts.extraKeys && !query) {
        const k = e.key.toLowerCase();
        if (opts.extraKeys[k] !== undefined) {
          e.preventDefault();
          resolve(opts.extraKeys[k]);
          return;
        }
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (listMode || query) {
          focusIdx = Math.min(focusIdx + 1, filtered.length - 1);
        } else {
          // grid row+1
          const r = focusIdx % rows;
          if (r < rows - 1) focusIdx++;
        }
        render();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (listMode || query) {
          focusIdx = Math.max(focusIdx - 1, 0);
        } else {
          const r = focusIdx % rows;
          if (r > 0) focusIdx--;
        }
        render();
      } else if (!listMode && !query) {
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          if (focusIdx + rows < items.length) focusIdx += rows;
          render();
        } else if (e.key === 'ArrowLeft') {
          e.preventDefault();
          if (focusIdx - rows >= 0) focusIdx -= rows;
          render();
        }
      } else if (e.key === 'Tab') {
        e.preventDefault();
        focusIdx = (focusIdx + 1) % Math.max(1, visible.length);
        render();
      } else if (e.key === 'PageDown') {
        e.preventDefault();
        focusIdx = Math.min(focusIdx + 20, Math.max(0, visible.length - 1));
        render();
      } else if (e.key === 'PageUp') {
        e.preventDefault();
        focusIdx = Math.max(focusIdx - 20, 0);
        render();
      }
    });

    input.focus();
    render();
  });
}

// ── Autocomplete (set selection) ───────────────────────────────────────────
export function showAutocomplete(choices, promptText, opts = {}) {
  return new Promise(resolve => {
    const screen = _makeScreen();
    screen.className = 'screen';
    _navScreen(resolve);

    const prompt = document.createElement('div');
    prompt.className = 'prompt';
    prompt.textContent = promptText;
    screen.appendChild(prompt);

    const hint = document.createElement('div');
    hint.className = 'hint';
    hint.textContent = 'type to filter  •  ↑/↓ or tab to cycle  •  enter to confirm  •  esc to go back';
    screen.appendChild(hint);

    const searchWrap = document.createElement('div');
    searchWrap.className = 'search-wrap';
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Search sets…';
    input.autocomplete = 'off';
    input.spellcheck = false;
    searchWrap.appendChild(input);
    if (opts.showRefreshBtn) {
      const btn = document.createElement('button');
      btn.className = 'refresh-btn';
      btn.textContent = '↻ Refresh';
      btn.addEventListener('click', () => resolve('__refresh__'));
      searchWrap.appendChild(btn);
    }
    screen.appendChild(searchWrap);

    const list = document.createElement('div');
    list.className = 'list-box';
    screen.appendChild(list);

    let filtered = [...choices];
    let focusIdx = 0;

    function render() {
      focusIdx = Math.min(focusIdx, Math.max(0, filtered.length - 1));
      list.innerHTML = '';
      filtered.forEach((item, i) => {
        const el = document.createElement('div');
        el.className = 'list-item' + (i === focusIdx ? ' focused' : '');
        el.textContent = item;
        el.addEventListener('click', () => resolve(item));
        el.addEventListener('mouseenter', () => { if (!HOVER_CAPABLE) return; focusIdx = i; render(); });
        list.appendChild(el);
      });
      const focusedEl = list.children[focusIdx];
      if (focusedEl) focusedEl.scrollIntoView({ block: 'nearest' });
    }

    input.addEventListener('input', () => {
      const q = input.value.toLowerCase();
      filtered = choices.filter(c => c.toLowerCase().includes(q));
      focusIdx = 0;
      render();
    });

    _onKey(e => {
      if (e.key === 'Escape') { e.preventDefault(); resolve(null); return; }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (filtered[focusIdx]) resolve(filtered[focusIdx]);
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'Tab') {
        e.preventDefault();
        focusIdx = Math.min(focusIdx + 1, filtered.length - 1);
        render();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        focusIdx = Math.max(focusIdx - 1, 0);
        render();
      } else if (e.key === 'PageDown') {
        e.preventDefault();
        focusIdx = Math.min(focusIdx + 20, Math.max(0, filtered.length - 1));
        render();
      } else if (e.key === 'PageUp') {
        e.preventDefault();
        focusIdx = Math.max(focusIdx - 20, 0);
        render();
      }
    });

    input.focus();
    render();
  });
}

// ── Multi-select (card selection) ──────────────────────────────────────────
export function showMultiSelect(items, promptText, opts = {}) {
  return new Promise(resolve => {
    const screen = _makeScreen();
    screen.className = 'screen';
    _navScreen(resolve);

    const itemMeta   = opts.itemMeta || null;
    const hasNumbers = !!(itemMeta && itemMeta.some(m => m && m.number));

    const prompt = document.createElement('div');
    prompt.className = 'prompt';
    prompt.textContent = promptText;
    screen.appendChild(prompt);

    // Search bar
    const searchWrap = document.createElement('div');
    searchWrap.className = 'search-wrap';
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search cards…';
    searchInput.autocomplete = 'off';
    searchInput.spellcheck = false;
    searchWrap.appendChild(searchInput);
    screen.appendChild(searchWrap);

    // Card grid
    const grid = document.createElement('div');
    grid.className = 'card-grid';
    grid.tabIndex = 0;
    screen.appendChild(grid);

    // Action bar
    const bar = document.createElement('div');
    bar.className = 'action-bar';

    function actionSpan(key, label, onClick) {
      const el = document.createElement('span');
      el.className = 'kbd' + (onClick ? ' clickable' : '');
      el.innerHTML = `<span>${key}</span> ${label}`;
      if (onClick) el.addEventListener('click', onClick);
      return el;
    }

    bar.appendChild(actionSpan('Space', 'Toggle'));
    bar.appendChild(actionSpan('Enter', 'Confirm', () => doConfirm()));
    bar.appendChild(actionSpan('A', 'All', () => selectAll()));
    bar.appendChild(actionSpan('D', 'None', () => selectNone()));
    bar.appendChild(actionSpan('I', 'Invert', () => invertSelection()));
    if (hasNumbers) bar.appendChild(actionSpan('Z', 'Sort #/A-Z', () => toggleSort()));
    bar.appendChild(actionSpan('S', 'Save', () => saveCards()));
    bar.appendChild(actionSpan('L', 'Load', () => fileInput.click()));
    bar.appendChild(actionSpan('R', 'Restart', () => doRestart()));
    bar.appendChild(actionSpan('Q', 'Quit', () => doQuit()));

    const countEl = document.createElement('span');
    countEl.className = 'count';
    bar.appendChild(countEl);
    screen.appendChild(bar);

    // Hidden file input for Load
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = '.txt';
    fileInput.style.display = 'none';
    screen.appendChild(fileInput);

    const selected = new Set();
    let undoPrev   = null;
    let sortMode   = hasNumbers ? 'number' : 'alpha';
    let focusIdx   = 0;
    let query      = '';
    let cardCols   = _responsiveCols(3);

    if (opts.initialSelected) {
      for (const name of opts.initialSelected) {
        const i = items.indexOf(name);
        if (i >= 0) selected.add(i);
      }
    }

    function cardNumSortKey(i) {
      const m = itemMeta && itemMeta[i];
      if (!m || !m.number) return Infinity;
      const n = parseInt(m.number.split('/')[0].trim(), 10);
      return isNaN(n) ? Infinity : n;
    }

    function printingOrder(i) {
      const m = itemMeta && itemMeta[i];
      const p = m && m.printing;
      return (!p || p === 'Normal') ? 0 : 1;
    }

    function buildOrder() {
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

    let sortedOrder = buildOrder();

    function getDisplayOrder() {
      if (!query) return sortedOrder;
      const q = query.toLowerCase();
      return sortedOrder.filter(i => items[i].toLowerCase().includes(q));
    }

    function formatLabel(origIdx) {
      let label = items[origIdx];
      if (sortMode === 'number' && itemMeta) {
        const m = itemMeta[origIdx];
        if (m && m.number) {
          const n = parseInt(m.number.split('/')[0].trim(), 10);
          label = `${isNaN(n) ? m.number : n}  ${label}`;
        }
      }
      return label;
    }

    function render() {
      const displayOrder = getDisplayOrder();
      focusIdx = Math.min(focusIdx, Math.max(0, displayOrder.length - 1));
      countEl.textContent = `${selected.size} / ${items.length} selected`;
      if (opts.onSelectionChange) opts.onSelectionChange(toNames());
      cardCols = _responsiveCols(3);
      grid.style.gridTemplateColumns = `repeat(${cardCols}, 1fr)`;
      grid.innerHTML = '';

      displayOrder.forEach((origIdx, displayI) => {
        const isFocused = displayI === focusIdx;
        const isChecked = selected.has(origIdx);
        const el = document.createElement('div');
        el.className = 'card-item' +
          (isChecked ? ' checked' : '') +
          (isFocused ? ' focused' : '');
        el.textContent = (isChecked ? '[x] ' : '[ ] ') + formatLabel(origIdx);
        el.addEventListener('click', () => {
          focusIdx = displayI;
          undoPrev = new Set(selected);
          selected.has(origIdx) ? selected.delete(origIdx) : selected.add(origIdx);
          render();
        });
        el.addEventListener('mouseenter', () => { if (!HOVER_CAPABLE) return; focusIdx = displayI; render(); });
        grid.appendChild(el);
      });

      const focusedEl = grid.children[focusIdx];
      if (focusedEl) focusedEl.scrollIntoView({ block: 'nearest' });
    }

    searchInput.addEventListener('input', () => {
      query    = searchInput.value;
      focusIdx = 0;
      render();
    });

    function toNames() {
      // Return names in original sorted order
      return sortedOrder.filter(i => selected.has(i)).map(i => items[i]);
    }

    function saveCards() {
      const names = toNames();
      if (!names.length) return;
      const blob = new Blob([names.join('\n')], { type: 'text/plain' });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url;
      a.download = 'cards.txt';
      a.click();
      URL.revokeObjectURL(url);
    }

    fileInput.addEventListener('change', () => {
      const file = fileInput.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = e => {
        const lines = e.target.result.split('\n').map(l => l.trim()).filter(Boolean);
        const valid = lines.filter(n => items.includes(n));
        undoPrev = new Set(selected);
        selected.clear();
        for (const name of valid) {
          const i = items.indexOf(name);
          if (i >= 0) selected.add(i);
        }
        render();
      };
      reader.readAsText(file);
    });

    function doConfirm()  { resolve({ action: 'confirm', selected: toNames() }); }
    function doRestart()  { resolve({ action: 'restart', selected: [] }); }
    function doQuit()     { resolve({ action: 'exit', selected: [] }); }

    function selectAll() {
      undoPrev = new Set(selected);
      for (let i = 0; i < items.length; i++) selected.add(i);
      render();
    }

    function selectNone() {
      undoPrev = new Set(selected);
      selected.clear();
      render();
    }

    function invertSelection() {
      undoPrev = new Set(selected);
      for (let i = 0; i < items.length; i++) {
        selected.has(i) ? selected.delete(i) : selected.add(i);
      }
      render();
    }

    function undoLast() {
      if (undoPrev === null) return;
      selected.clear();
      for (const i of undoPrev) selected.add(i);
      undoPrev = null;
      render();
    }

    function toggleSort() {
      if (!hasNumbers) return;
      sortMode    = sortMode === 'number' ? 'alpha' : 'number';
      sortedOrder = buildOrder();
      focusIdx    = 0;
      render();
    }

    _onKey(e => {
      const displayOrder = getDisplayOrder();

      if (e.key === 'Enter') {
        e.preventDefault();
        doConfirm();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        doRestart();
      } else if (e.key === ' ') {
        // Only handle space if search isn't focused
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        if (displayOrder[focusIdx] !== undefined) {
          const origIdx = displayOrder[focusIdx];
          undoPrev = new Set(selected);
          selected.has(origIdx) ? selected.delete(origIdx) : selected.add(origIdx);
          render();
        }
      } else if (e.key === 'ArrowDown') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        focusIdx = Math.min(focusIdx + cardCols, displayOrder.length - 1);
        render();
      } else if (e.key === 'ArrowUp') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        focusIdx = Math.max(focusIdx - cardCols, 0);
        render();
      } else if (e.key === 'ArrowRight') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        focusIdx = Math.min(focusIdx + 1, displayOrder.length - 1);
        render();
      } else if (e.key === 'ArrowLeft') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        focusIdx = Math.max(focusIdx - 1, 0);
        render();
      } else if (e.key === 'PageDown') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        focusIdx = Math.min(focusIdx + cardCols * 10, displayOrder.length - 1);
        render();
      } else if (e.key === 'PageUp') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        focusIdx = Math.max(focusIdx - cardCols * 10, 0);
        render();
      } else if (e.key === 's' || e.key === 'S') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        saveCards();
      } else if (e.key === 'l' || e.key === 'L') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        fileInput.click();
      } else if (e.key === 'a' || e.key === 'A') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        selectAll();
      } else if (e.key === 'd' || e.key === 'D') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        selectNone();
      } else if (e.key === 'i' || e.key === 'I') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        invertSelection();
      } else if (e.key === 'u' || e.key === 'U') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        undoLast();
      } else if ((e.key === 'z' || e.key === 'Z') && hasNumbers) {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        toggleSort();
      } else if (e.key === 'r' || e.key === 'R') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        doRestart();
      } else if (e.key === 'q' || e.key === 'Q') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        doQuit();
      }
    });

    _onResize(() => render());

    render();
  });
}

// ── Progress bar factory ───────────────────────────────────────────────────
function _makeProgressScreen(total, headerText) {
  const screen = _makeScreen();
  screen.className = 'screen';

  const wrap = document.createElement('div');
  wrap.className = 'progress-screen';

  const hdr = document.createElement('div');
  hdr.className = 'progress-header';
  hdr.textContent = headerText;
  wrap.appendChild(hdr);

  const track = document.createElement('div');
  track.className = 'progress-track';
  const fill = document.createElement('div');
  fill.className = 'progress-fill';
  track.appendChild(fill);
  wrap.appendChild(track);

  const status = document.createElement('div');
  status.className = 'progress-status';
  const statusLeft  = document.createElement('span');
  const statusRight = document.createElement('span');
  status.appendChild(statusLeft);
  status.appendChild(statusRight);
  wrap.appendChild(status);

  const debugWrap = document.createElement('div');
  debugWrap.className = 'progress-debug';
  wrap.appendChild(debugWrap);

  screen.appendChild(wrap);

  let done = 0;

  function onComplete(label) {
    done++;
    const pct = Math.round((done / total) * 100);
    fill.style.width = `${pct}%`;
    statusLeft.textContent  = `[${done}/${total}] ${label}`;
    statusRight.textContent = `${pct}%`;
  }

  function onPage(cardName, count) {
    statusLeft.textContent = `[${done}/${total}] ${cardName} [${count}]`;
  }

  function onDebug(text) {
    const line = document.createElement('div');
    line.className = 'debug-line';
    line.textContent = text;
    debugWrap.appendChild(line);
    debugWrap.scrollTop = debugWrap.scrollHeight;
  }

  return { onComplete, onPage, onDebug };
}

export function showProgress(total) {
  return _makeProgressScreen(total, 'Scraping card listings…');
}

export function showFilterProgress(total) {
  const pb = _makeProgressScreen(total, 'Gathering set data…');
  return { onComplete: pb.onComplete, onDebug: pb.onDebug };
}

// ── Cart progress ──────────────────────────────────────────────────────────
export function showCartProgress(total, summaryInfo) {
  const screen = _makeScreen();
  screen.className = 'screen';

  const wrap = document.createElement('div');
  wrap.className = 'progress-screen';

  const hdr = document.createElement('div');
  hdr.className = 'progress-header';
  hdr.textContent = 'Creating cart — adding items to TCGPlayer…';
  wrap.appendChild(hdr);

  const sub = document.createElement('div');
  sub.className = 'log-muted';
  sub.style.marginBottom = '8px';
  sub.textContent = 'Headless browser is building your cart. This may take a moment.';
  wrap.appendChild(sub);

  if (summaryInfo) {
    const info = document.createElement('div');
    info.style.cssText = 'color:var(--secondary);font-size:13px;border-top:1px solid #333;padding-top:6px;margin-bottom:8px;';
    info.innerHTML = `
      <div>${summaryInfo.cartTitle}</div>
      <div>Cards: ${summaryInfo.cards}  •  Sellers: ${summaryInfo.sellers}  •  Subtotal: $${summaryInfo.rawCost.toFixed(2)}  •  Shipping: $${summaryInfo.shipping.toFixed(2)}  •  Total: $${summaryInfo.total.toFixed(2)}</div>
    `;
    wrap.appendChild(info);
  }

  const track = document.createElement('div');
  track.className = 'progress-track';
  const fill = document.createElement('div');
  fill.className = 'progress-fill';
  fill.style.background = 'var(--accent)';
  track.appendChild(fill);
  wrap.appendChild(track);

  const status = document.createElement('div');
  status.className = 'progress-status';
  const statusLeft  = document.createElement('span');
  const statusRight = document.createElement('span');
  status.appendChild(statusLeft);
  status.appendChild(statusRight);
  wrap.appendChild(status);

  screen.appendChild(wrap);

  let done = 0;
  return function update(cardName) {
    done++;
    const pct = Math.round((done / total) * 100);
    fill.style.width = `${pct}%`;
    statusLeft.textContent  = `[${done}/${total}] ${cardName}`;
    statusRight.textContent = `${pct}%`;
  };
}

// ── Cart result ────────────────────────────────────────────────────────────
export function showCartResult(result) {
  // Append to the current screen rather than replacing it
  if (!_screen) return;
  // Remove progress bar if present
  _screen.querySelectorAll('.progress-track, .progress-status').forEach(el => el.remove());

  const { cartKey, failedItems = [] } = result;
  const div = document.createElement('div');
  div.className = 'cart-result';

  if (failedItems.length === 0) {
    const ok = document.createElement('div');
    ok.className = 'cart-result-ok';
    ok.textContent = '✓ All items added to cart successfully!';
    div.appendChild(ok);
  } else {
    const warn = document.createElement('div');
    warn.className = 'cart-result-warn';
    warn.textContent = `Cart done — ${failedItems.length} item(s) could not be added:`;
    div.appendChild(warn);
    for (const item of failedItems) {
      const line = document.createElement('div');
      line.className = 'cart-result-item';
      line.textContent = `• ${item.card}: ${item.reason}`;
      div.appendChild(line);
    }
  }

  if (cartKey) {
    div.appendChild(buildCartHandoff());
  }

  _screen.appendChild(div);
}

// The cart is built server-side, so its TCGPlayer session cookie lives on
// the backend, not in the user's real browser. There's no way to hand that
// cookie across origins directly, so we use a bookmarklet: a small script
// the user installs once and clicks while on tcgplayer.com, which pulls the
// latest cart key from our backend and sets TCGPlayer's own
// `StoreCart_PRODUCTION` cookie itself (same format their own site code
// uses). It talks to the backend over a raw WebSocket rather than fetch() —
// TCGPlayer's CSP `connect-src` blocks fetch/XHR to arbitrary origins but
// allows unrestricted `wss:` (confirmed against their live CSP header), and
// the backend already speaks this JSON-RPC protocol on /ws.
function buildCartBookmarklet() {
  const code = `(function(){try{var ws=new WebSocket('${BACKEND_WS_URL}');var done=false;var fail=function(m){if(done)return;done=true;alert('masterset: '+m);};ws.onerror=function(){fail('could not reach the backend.');};ws.onopen=function(){ws.send(JSON.stringify({id:1,method:'get_pending_cart',params:{}}));};ws.onmessage=function(ev){if(done)return;var msg=JSON.parse(ev.data);if(msg.error){fail(msg.error);return;}var cartKey=msg.result&&msg.result.cartKey;if(!cartKey){fail('no cart is ready yet — build one first, then click this again.');return;}done=true;document.cookie='StoreCart_PRODUCTION=CK='+cartKey+'&Ignore=false;domain=.tcgplayer.com;path=/';location.href='https://www.tcgplayer.com/cart';};setTimeout(function(){fail('timed out reaching the backend.');},8000);}catch(e){alert('masterset: '+e.message);}})();`;
  return 'javascript:' + encodeURIComponent(code);
}

function buildCartHandoff() {
  const wrap = document.createElement('div');
  wrap.className = 'cart-result-handoff';

  const intro = document.createElement('div');
  intro.className = 'cart-result-handoff-intro';
  intro.textContent = 'Your optimized cart is built and waiting on the backend. Since this app runs on a different site than tcgplayer.com, loading it into your real browser takes one extra (one-time) step:';
  wrap.appendChild(intro);

  const step1 = document.createElement('div');
  step1.className = 'cart-result-step';
  const openLink = document.createElement('a');
  openLink.href = 'https://www.tcgplayer.com/';
  openLink.target = '_blank';
  openLink.rel = 'noopener';
  openLink.textContent = 'Open TCGPlayer.com →';
  step1.appendChild(document.createTextNode('1. '));
  step1.appendChild(openLink);
  wrap.appendChild(step1);

  const step2 = document.createElement('div');
  step2.className = 'cart-result-step';
  const bookmarklet = document.createElement('a');
  bookmarklet.href = buildCartBookmarklet();
  bookmarklet.className = 'cart-result-bookmarklet';
  bookmarklet.textContent = '📌 Load Masterset Cart';
  bookmarklet.title = 'Drag this link to your bookmarks bar';
  step2.appendChild(document.createTextNode('2. Drag '));
  step2.appendChild(bookmarklet);
  step2.appendChild(document.createTextNode(' to your bookmarks bar (once). While on any tcgplayer.com page, click it to load your latest optimized cart.'));
  wrap.appendChild(step2);

  return wrap;
}

// ── Confirm dialog ─────────────────────────────────────────────────────────
export function showConfirm(question) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    const modal = document.createElement('div');
    modal.className = 'modal';

    const q = document.createElement('div');
    q.className = 'modal-question';
    q.textContent = question;
    modal.appendChild(q);

    const btns = document.createElement('div');
    btns.className = 'modal-btns';

    const yesBtn = document.createElement('button');
    yesBtn.className = 'modal-btn focused';
    yesBtn.textContent = 'Yes';

    const noBtn = document.createElement('button');
    noBtn.className = 'modal-btn';
    noBtn.textContent = 'No';

    btns.appendChild(yesBtn);
    btns.appendChild(noBtn);
    modal.appendChild(btns);

    const hint = document.createElement('div');
    hint.className = 'modal-hint';
    hint.textContent = '← / → or Tab to move  •  Enter to confirm  •  Y / N hotkeys';
    modal.appendChild(hint);

    overlay.appendChild(modal);
    app.appendChild(overlay);

    let choice = 0; // 0=yes, 1=no
    const btnEls = [yesBtn, noBtn];

    function renderBtns() {
      btnEls.forEach((b, i) => b.classList.toggle('focused', i === choice));
    }

    let finished = false;
    function done(val) {
      if (finished) return;
      finished = true;
      document.removeEventListener('keydown', kh);
      overlay.remove();
      resolve(val);
    }

    const kh = e => {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Tab') {
        e.preventDefault(); choice = 1 - choice; renderBtns();
      } else if (e.key === 'Enter') {
        e.preventDefault(); done(choice === 0);
      } else if (e.key === 'y' || e.key === 'Y') {
        done(true);
      } else if (e.key === 'n' || e.key === 'N' || e.key === 'Escape') {
        done(false);
      }
    };
    document.addEventListener('keydown', kh);

    yesBtn.onclick = () => done(true);
    noBtn.onclick  = () => done(false);
  });
}

// ── Wait for keypress ──────────────────────────────────────────────────────
export function waitForKey(message) {
  return new Promise(resolve => {
    if (!_screen) { resolve(); return; }

    const bar = document.createElement('div');
    bar.className = 'wait-key-bar';
    bar.textContent = message;
    _screen.appendChild(bar);

    let finished = false;
    function finish() {
      if (finished) return;
      finished = true;
      document.removeEventListener('keydown', kh);
      bar.remove();
      resolve();
    }

    // Let the persistent nav icons (e.g. Home on the empty-binder screen) resolve
    // this wait too, not just Enter/click — otherwise a click there is a silent no-op.
    _navScreen(() => finish());

    const kh = e => {
      if (['Enter', ' ', 'q', 'Q'].includes(e.key)) {
        e.preventDefault();
        finish();
      }
    };
    document.addEventListener('keydown', kh);
    bar.addEventListener('click', finish);
  });
}

// ── Cart summary utilities ─────────────────────────────────────────────────
export function calcShipping(cart) {
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

export function buildSummary(cart) {
  const sellers = new Set(cart.map(i => i.seller).filter(Boolean));
  const rawCost = cart.reduce((s, i) => s + (i.price || 0), 0);
  const shipping = calcShipping(cart);
  return { cards: cart.length, sellers: sellers.size, rawCost, shipping, total: rawCost + shipping };
}

// ── Binder page (the dynamic optimizer, now the binder's landing screen) ────
// Adapted from the original single-set optimizer. Additions: a live per-card list of
// the binder's contents (name · set · price · delete) in place of the old inline
// notice box; the filter-relaxation notices moved behind a badge button; and
// refresh / clear-all actions. Filter toggles and per-card deletes re-optimize in
// place (scoped to the current binder card ids); refresh and clear-all resolve an
// action that app.js drives (they need a scrape progress screen / empty state).
export function showBinder(firstCart, defaultCart, filterOptions, defaultFilters = {}, extra = {}) {
  return new Promise(resolve => {
    const screen = _makeScreen();
    screen.className = 'screen optimizer binder';
    _navScreen(resolve);

    const CONDITIONS  = filterOptions.conditions  || [];
    const QUALS       = filterOptions.sellerQuals || [];
    const QUAL_LABELS = { Verified: 'Verified Seller', Direct: 'Direct', WPN: 'WPN' };

    const defaultConds = defaultFilters.conditions || ['Near Mint', 'Lightly Played'];
    const defaultQuals = defaultFilters.quals || [];
    const condChecked  = new Set(defaultConds.filter(c => CONDITIONS.includes(c)));
    const qualChecked  = new Set(defaultQuals.filter(q => QUALS.includes(q)));

    // Live, mutable binder state. `cards` mirrors the binder localStorage entries
    // ({ id, displayName, setName, ... }); firstCartCur/userCart hold the latest
    // optimize result so per-card prices and totals track deletes + filter changes.
    let cards            = (extra.cards || []).slice();
    let firstCartCur     = firstCart;
    let userCart         = defaultCart;
    let currentOverrides = extra.initialOverrides || [];
    const backendLogs    = [];
    let isCalc           = false;
    let debounceId       = null;
    let noticesOpen      = false;

    if (extra.onLog) extra.onLog(text => { backendLogs.push(text); renderNoticesBadge(); if (noticesOpen) renderNoticesPanel(); });

    const summaries = [
      { ...buildSummary(firstCartCur), cards: cards.length },
      buildSummary(userCart),
    ];

    // ── Zone tracking: 0=carts, 1=filters ─────────────────────────────────
    let zone        = 0;
    let selectedCart = 1;
    let filterCol   = 0;
    const filterRows = [0, 0];

    // ── Description & hint ─────────────────────────────────────────────────
    const desc = document.createElement('div');
    desc.className = 'optimizer-desc';
    screen.appendChild(desc);

    const hintEl = document.createElement('div');
    hintEl.className = 'optimizer-hint';
    screen.appendChild(hintEl);

    // ── Cart row ───────────────────────────────────────────────────────────
    const cartRow = document.createElement('div');
    cartRow.className = 'cart-row';

    const cartBoxEls  = [0, 1].map(i => {
      const b = document.createElement('div');
      b.className = 'cart-box';
      b.tabIndex  = 0;
      b.addEventListener('click', () => { zone = 0; selectedCart = i; confirmCart(); });
      b.addEventListener('mouseenter', () => { if (!HOVER_CAPABLE) return; if (zone === 0) { selectedCart = i; renderAll(); } });
      return b;
    });

    const savingsBox = document.createElement('div');
    savingsBox.className = 'savings-box';

    cartBoxEls.forEach(b => cartRow.appendChild(b));
    cartRow.appendChild(savingsBox);
    screen.appendChild(cartRow);

    // ── Filter row ─────────────────────────────────────────────────────────
    const filterRow = document.createElement('div');
    filterRow.className = 'filter-row';

    const filterBoxEls = [0, 1].map(col => {
      const box = document.createElement('div');
      box.className = 'filter-box';
      const title = document.createElement('div');
      title.className = 'filter-title';
      title.textContent = col === 0 ? 'Filter: Condition' : 'Filter: Seller Qualification';
      box.appendChild(title);
      box.addEventListener('click', () => { zone = 1; filterCol = col; renderAll(); });
      filterRow.appendChild(box);
      return box;
    });
    screen.appendChild(filterRow);

    // ── Binder card list (takes the old notice box's space) ────────────────
    const listWrap = document.createElement('div');
    listWrap.className = 'binder-list-wrap';
    const listHead = document.createElement('div');
    listHead.className = 'binder-list-head';
    listWrap.appendChild(listHead);
    const listGrid = document.createElement('div');
    listGrid.className = 'binder-list';
    listGrid.style.gridTemplateColumns = `repeat(${_responsiveCols(3)}, 1fr)`;
    listWrap.appendChild(listGrid);
    screen.appendChild(listWrap);
    _onResize(() => { listGrid.style.gridTemplateColumns = `repeat(${_responsiveCols(3)}, 1fr)`; });

    // ── Notices panel (hidden until toggled from the action bar) ───────────
    const noticesPanel = document.createElement('div');
    noticesPanel.className = 'notices-panel';
    screen.appendChild(noticesPanel);

    // ── Action bar ─────────────────────────────────────────────────────────
    const actionsEl = document.createElement('div');
    actionsEl.className = 'optimizer-actions';

    function actionHint(key, label, onClick) {
      const el = document.createElement('span');
      el.className = 'hint clickable';
      el.innerHTML = `<span style="color:var(--secondary)">[${key}]</span> ${label}`;
      el.addEventListener('click', onClick);
      return el;
    }

    const noticesBtn = document.createElement('span');
    noticesBtn.className = 'hint clickable notices-btn';
    noticesBtn.addEventListener('click', () => toggleNotices());

    actionsEl.appendChild(actionHint('Enter', 'Confirm cart', () => confirmCart()));
    actionsEl.appendChild(actionHint('Tab', 'Switch zone', () => switchZone()));
    actionsEl.appendChild(noticesBtn);
    actionsEl.appendChild(actionHint('F', 'Refresh prices', () => doRefresh()));
    actionsEl.appendChild(actionHint('C', 'Clear binder', () => doClear()));
    actionsEl.appendChild(actionHint('Esc', 'Home', () => goHome()));
    screen.appendChild(actionsEl);

    // ── Render helpers ──────────────────────────────────────────────────────
    const CART_TITLES = ['FIRST LISTING', 'DYNAMIC OPTIMIZED'];
    const CHEAP_GREEN = '#88cc88';
    const SPINNER     = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'];
    let spinFrame = 0;
    let spinTimer = null;

    function startSpinner() {
      if (spinTimer) return;
      spinTimer = setInterval(() => { spinFrame = (spinFrame + 1) % SPINNER.length; renderCartBox(1); }, 80);
    }
    function stopSpinner() {
      if (spinTimer) { clearInterval(spinTimer); spinTimer = null; }
    }

    function renderCartBox(i) {
      const box    = cartBoxEls[i];
      const isSel  = zone === 0 && selectedCart === i;
      const s      = summaries[i];
      const cheapIdx = (!isCalc && summaries[0].total !== summaries[1].total)
        ? (summaries[0].total < summaries[1].total ? 0 : 1) : -1;
      const isCheap = cheapIdx === i;

      box.classList.toggle('focused',  isSel);
      box.classList.toggle('cheapest', isCheap);

      const col = isSel ? PRIMARY : SECONDARY;

      if (i === 1 && isCalc) {
        box.innerHTML = `
          <div class="cart-title" style="color:${col}">${CART_TITLES[i]}</div>
          <div class="cart-stat"  style="color:${col}">${SPINNER[spinFrame]} Recalculating…</div>`;
        return;
      }

      box.innerHTML = `
        <div class="cart-title" style="color:${isCheap ? CHEAP_GREEN : col}">${CART_TITLES[i]}</div>
        <div class="cart-stat"  style="color:${col}">Requested: ${s.cards}</div>
        <div class="cart-stat"  style="color:${col}">Sellers:  ${s.sellers}</div>
        <div class="cart-stat"  style="color:${col}">Subtotal: $${s.rawCost.toFixed(2)}</div>
        <div class="cart-stat"  style="color:${col}">Shipping: $${s.shipping.toFixed(2)}</div>
        <div class="cart-total" style="color:${col}">Total:    $${s.total.toFixed(2)}</div>`;
    }

    function renderSavings() {
      const savings = !isCalc ? summaries[0].total - summaries[1].total : 0;
      if (savings > 0.005) {
        savingsBox.classList.add('show');
        const donate = Math.ceil(savings * 0.20);
        savingsBox.innerHTML = `
          <div class="savings-label">YOU SAVED</div>
          <div class="savings-amount">$${savings.toFixed(2)}</div>
          <div class="savings-sub">vs. First Listing</div>
          <div class="savings-sub" style="margin-top:4px">Consider donating ~20%:</div>
          <div class="savings-donate"><a href="https://buymeacoffee.com/jdenaro" target="_blank" rel="noopener" style="color:#ffdd00;text-decoration:none">$${donate}.00 ☕</a></div>`;
        // Shrink cart boxes to 38% each
        cartBoxEls[0].style.flex = '0 0 38%';
        cartBoxEls[1].style.flex = '0 0 38%';
      } else {
        savingsBox.classList.remove('show');
        cartBoxEls[0].style.flex = '1';
        cartBoxEls[1].style.flex = '1';
      }
    }

    function renderFilterBox(col) {
      const box     = filterBoxEls[col];
      const isActive = zone === 1 && filterCol === col;
      const items   = col === 0 ? CONDITIONS : QUALS;
      const checked = col === 0 ? condChecked : qualChecked;
      const cursor  = filterRows[col];
      box.classList.toggle('active', isActive);

      // Remove old items (keep title)
      while (box.children.length > 1) box.removeChild(box.lastChild);

      items.forEach((item, idx) => {
        const label     = col === 1 ? (QUAL_LABELS[item] || item) : item;
        const isChecked = checked.has(item);
        const isCursor  = isActive && idx === cursor;
        const el        = document.createElement('div');
        el.className    = 'filter-item' + (isChecked ? ' checked' : '') + (isCursor ? ' focused' : '');
        el.textContent  = (isChecked ? '[x] ' : '[ ] ') + label;
        el.addEventListener('click', () => {
          filterCol = col; zone = 1; filterRows[col] = idx;
          if (checked.has(item)) checked.delete(item); else checked.add(item);
          reoptimize();
          renderAll();
        });
        el.addEventListener('mouseenter', () => { if (!HOVER_CAPABLE) return; filterRows[col] = idx; renderFilterBox(col); });
        box.appendChild(el);
      });
    }

    // Price of a card in the currently selected cart, keyed by the stable cardId the
    // backend now stamps on every cart entry (so duplicate names never mismap).
    function priceForCard(id) {
      const cart = selectedCart === 0 ? firstCartCur : userCart;
      const e = cart.find(x => x.cardId === id);
      if (!e || e.seller == null) return null;
      return e.price || 0;
    }

    function renderList() {
      listHead.textContent = `Binder — ${cards.length} card${cards.length === 1 ? '' : 's'}`;
      listGrid.innerHTML = '';
      for (const c of cards) {
        const row = document.createElement('div');
        row.className = 'binder-card';

        const nameEl = document.createElement('span');
        nameEl.className = 'binder-card-name';
        nameEl.textContent = c.displayName;
        nameEl.title = c.displayName;

        const setEl = document.createElement('span');
        setEl.className = 'binder-card-set';
        setEl.textContent = c.setName || '';
        setEl.title = c.setName || '';

        const price = priceForCard(c.id);
        const priceEl = document.createElement('span');
        priceEl.className = 'binder-card-price';
        priceEl.textContent = price == null ? '—' : `$${price.toFixed(2)}`;

        const del = document.createElement('span');
        del.className = 'binder-card-del';
        del.textContent = '✕';
        del.title = 'Remove from binder';
        del.addEventListener('click', () => deleteCard(c.id));

        row.appendChild(nameEl);
        row.appendChild(setEl);
        row.appendChild(priceEl);
        row.appendChild(del);
        listGrid.appendChild(row);
      }
    }

    function renderNoticesBadge() {
      const n = currentOverrides.length;
      noticesBtn.innerHTML =
        `<span style="color:var(--secondary)">[N]</span> Notices` +
        (n > 0 ? ` <span class="notices-bubble">${n}</span>` : '');
    }

    function renderNoticesPanel() {
      noticesPanel.classList.toggle('show', noticesOpen);
      if (!noticesOpen) return;
      noticesPanel.innerHTML = '';
      const title = document.createElement('div');
      title.className = 'notices-panel-title';
      title.textContent = 'Notices — filters relaxed for these cards';
      noticesPanel.appendChild(title);
      if (!currentOverrides.length && !backendLogs.length) {
        const el = document.createElement('div');
        el.className = 'notice-debug';
        el.textContent = 'No relaxations — every card matched your filters.';
        noticesPanel.appendChild(el);
      }
      for (const o of currentOverrides) {
        const el = document.createElement('div');
        el.className = 'notice-warn';
        el.textContent = `⚠ ${o.name}: ${o.applied}`;
        noticesPanel.appendChild(el);
      }
      for (const line of backendLogs) {
        const el = document.createElement('div');
        el.className = 'notice-debug';
        el.textContent = line;
        noticesPanel.appendChild(el);
      }
    }

    function toggleNotices() { noticesOpen = !noticesOpen; renderNoticesPanel(); }

    function renderHint() {
      hintEl.textContent = zone === 0
        ? 'CARTS  ←/→ navigate  •  Enter confirm  •  Tab: filters  •  N notices  •  F refresh  •  C clear  •  Esc home'
        : 'FILTERS  ←/→ columns  •  ↑/↓ navigate  •  Space toggle  •  Tab: carts  •  Esc home';
    }

    function renderAll() {
      desc.textContent = 'Choose a cart, tune filters, or manage the cards in your binder below.';
      renderSavings();
      renderCartBox(0); renderCartBox(1);
      renderFilterBox(0); renderFilterBox(1);
      renderList();
      renderNoticesBadge();
      renderNoticesPanel();
      renderHint();
    }

    // ── Re-optimize, scoped to the binder's current card ids ───────────────
    function currentCardIds() { return cards.map(c => c.id); }

    function reoptimize({ immediate = false } = {}) {
      if (extra.onFiltersChange) extra.onFiltersChange({ conditions: [...condChecked], quals: [...qualChecked] });
      if (debounceId) clearTimeout(debounceId);
      isCalc = true; startSpinner();
      const run = async () => {
        try {
          const result = await call('optimize_filtered', {
            conditions:  [...condChecked],
            sellerQuals: [...qualChecked],
            cardIds:     currentCardIds(),
          });
          userCart         = result.cart || [];
          firstCartCur     = result.firstCart || firstCartCur;
          currentOverrides = result.overrides || [];
          summaries[0]     = { ...buildSummary(firstCartCur), cards: cards.length };
          summaries[1]     = buildSummary(userCart);
        } catch (_) {}
        finally {
          isCalc = false; stopSpinner();
          renderAll();
        }
      };
      if (immediate) run(); else debounceId = setTimeout(run, 300);
    }

    function cleanupTimers() {
      if (spinTimer) clearInterval(spinTimer);
      if (debounceId) clearTimeout(debounceId);
    }

    // ── Per-card delete ────────────────────────────────────────────────────
    function deleteCard(id) {
      cards = cards.filter(c => c.id !== id);
      if (extra.onDeleteCard) extra.onDeleteCard(id);
      if (!cards.length) { cleanupTimers(); resolve({ action: 'empty' }); return; }
      renderList();               // instant visual removal
      reoptimize({ immediate: true });
    }

    // ── Shared actions (keyboard + mouse) ───────────────────────────────────
    function switchZone() {
      zone = 1 - zone;
      renderAll();
    }

    function confirmCart() {
      if (selectedCart === 1 && isCalc) return;
      const carts = [firstCartCur, userCart];
      cleanupTimers();
      resolve({
        action: 'confirm',
        cart: carts[selectedCart],
        cartTitle: CART_TITLES[selectedCart],
        summary: summaries[selectedCart],
      });
    }

    function doRefresh() { cleanupTimers(); resolve({ action: 'refresh' }); }
    function doClear()   { cleanupTimers(); resolve({ action: 'clear' }); }
    function goHome()    { cleanupTimers(); resolve({ action: 'home' }); }

    // ── Keyboard handling ──────────────────────────────────────────────────
    _onKey(e => {
      // While the notices panel is open, Esc closes it rather than leaving the page.
      if (noticesOpen && e.key === 'Escape') { e.preventDefault(); noticesOpen = false; renderNoticesPanel(); return; }
      if (e.key === 'Tab') {
        e.preventDefault();
        switchZone();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        if (zone === 0) {
          if (selectedCart > 0) { selectedCart--; renderAll(); }
        } else {
          if (filterCol > 0) { filterCol--; renderAll(); }
        }
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        if (zone === 0) {
          if (selectedCart < 1) { selectedCart++; renderAll(); }
        } else {
          if (filterCol < 1) { filterCol++; renderAll(); }
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (zone === 1 && filterRows[filterCol] > 0) {
          filterRows[filterCol]--;
          renderFilterBox(filterCol);
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (zone === 1) {
          const items = filterCol === 0 ? CONDITIONS : QUALS;
          if (filterRows[filterCol] < items.length - 1) {
            filterRows[filterCol]++;
            renderFilterBox(filterCol);
          }
        }
      } else if (e.key === ' ') {
        e.preventDefault();
        if (zone !== 1) return;
        const items   = filterCol === 0 ? CONDITIONS : QUALS;
        const checked = filterCol === 0 ? condChecked : qualChecked;
        const item    = items[filterRows[filterCol]];
        if (!item) return;
        if (checked.has(item)) checked.delete(item); else checked.add(item);
        reoptimize();
        renderFilterBox(filterCol);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        confirmCart();
      } else if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        toggleNotices();
      } else if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        doRefresh();
      } else if (e.key === 'c' || e.key === 'C') {
        e.preventDefault();
        doClear();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        goHome();
      }
    });

    if (extra.onFiltersChange) extra.onFiltersChange({ conditions: [...condChecked], quals: [...qualChecked] });
    renderAll();
  });
}

// ── Simple log output helpers (used during loading states) ─────────────────
export function showLogScreen(headerText) {
  const screen = _makeScreen();
  screen.className = 'screen';
  const logBox = document.createElement('div');
  logBox.className = 'log-box';
  screen.appendChild(logBox);

  function logLine(text, cls = 'log-secondary') {
    const el = document.createElement('div');
    el.className = cls;
    el.textContent = text;
    logBox.appendChild(el);
    logBox.scrollTop = logBox.scrollHeight;
  }

  if (headerText) logLine(headerText, 'log-primary');

  return {
    log:    text => logLine(text, 'log-secondary'),
    header: text => logLine(text, 'log-primary'),
    muted:  text => logLine(text, 'log-muted'),
    screen,
  };
}
