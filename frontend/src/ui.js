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

// ── Screen management ──────────────────────────────────────────────────────
const app = document.getElementById('app');
let _screen   = null;
let _keyClean = [];

function _clearScreen() {
  _keyClean.forEach(fn => document.removeEventListener('keydown', fn));
  _keyClean = [];
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
          el.addEventListener('mouseenter', () => { focusIdx = i; render(); });
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
            el.addEventListener('mouseenter', () => { focusIdx = capturedLinear; render(); });
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
        el.addEventListener('mouseenter', () => { focusIdx = i; render(); });
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

    const itemMeta   = opts.itemMeta || null;
    const hasNumbers = !!(itemMeta && itemMeta.some(m => m && m.number));

    const prompt = document.createElement('div');
    prompt.className = 'prompt';
    prompt.textContent = promptText;
    screen.appendChild(prompt);

    const hint = document.createElement('div');
    hint.className = 'hint';
    hint.textContent = 'space/click: toggle  •  enter: confirm  •  A: all  •  D: deselect all  •  I: invert' +
      (hasNumbers ? '  •  Z: sort #/A-Z' : '') + '  •  R: restart  •  Q: quit';
    screen.appendChild(hint);

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
    const countEl = document.createElement('span');
    countEl.className = 'count';
    bar.innerHTML = `
      <span class="kbd"><span>Enter</span> Confirm</span>
      <span class="kbd"><span>S</span> Save</span>
      <span class="kbd"><span>L</span> Load</span>
      <span class="kbd"><span>A</span> All</span>
      <span class="kbd"><span>D</span> None</span>
    `;
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
        el.addEventListener('mouseenter', () => { focusIdx = displayI; render(); });
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

    _onKey(e => {
      const displayOrder = getDisplayOrder();

      if (e.key === 'Enter') {
        e.preventDefault();
        resolve({ action: 'confirm', selected: toNames() });
      } else if (e.key === 'Escape') {
        e.preventDefault();
        resolve({ action: 'restart', selected: [] });
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
        focusIdx = Math.min(focusIdx + 3, displayOrder.length - 1);
        render();
      } else if (e.key === 'ArrowUp') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        focusIdx = Math.max(focusIdx - 3, 0);
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
        focusIdx = Math.min(focusIdx + 30, displayOrder.length - 1);
        render();
      } else if (e.key === 'PageUp') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        focusIdx = Math.max(focusIdx - 30, 0);
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
        undoPrev = new Set(selected);
        for (let i = 0; i < items.length; i++) selected.add(i);
        render();
      } else if (e.key === 'd' || e.key === 'D') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        undoPrev = new Set(selected);
        selected.clear();
        render();
      } else if (e.key === 'i' || e.key === 'I') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        undoPrev = new Set(selected);
        for (let i = 0; i < items.length; i++) {
          selected.has(i) ? selected.delete(i) : selected.add(i);
        }
        render();
      } else if (e.key === 'u' || e.key === 'U') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        if (undoPrev !== null) {
          selected.clear();
          for (const i of undoPrev) selected.add(i);
          undoPrev = null;
          render();
        }
      } else if ((e.key === 'z' || e.key === 'Z') && hasNumbers) {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        sortMode    = sortMode === 'number' ? 'alpha' : 'number';
        sortedOrder = buildOrder();
        focusIdx    = 0;
        render();
      } else if (e.key === 'r' || e.key === 'R') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        resolve({ action: 'restart', selected: [] });
      } else if (e.key === 'q' || e.key === 'Q') {
        if (document.activeElement === searchInput) return;
        e.preventDefault();
        resolve({ action: 'exit', selected: [] });
      }
    });

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
    bar.style.cssText = 'padding:6px 8px;color:#aaa;border-top:1px solid #333;';
    bar.textContent = message;
    _screen.appendChild(bar);

    const kh = e => {
      if (['Enter', ' ', 'q', 'Q'].includes(e.key)) {
        e.preventDefault();
        document.removeEventListener('keydown', kh);
        bar.remove();
        resolve();
      }
    };
    document.addEventListener('keydown', kh);
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

// ── Dynamic optimizer screen ───────────────────────────────────────────────
export function showDynamicOptimizer(firstCart, defaultCart, filterOptions, defaultFilters = {}, extra = {}) {
  return new Promise(resolve => {
    const screen = _makeScreen();
    screen.className = 'screen optimizer';

    const CONDITIONS  = filterOptions.conditions  || [];
    const QUALS       = filterOptions.sellerQuals || [];
    const QUAL_LABELS = { Verified: 'Verified Seller', Direct: 'Direct', WPN: 'WPN' };

    const defaultConds = defaultFilters.conditions || ['Near Mint', 'Lightly Played'];
    const defaultQuals = defaultFilters.quals || [];
    const condChecked  = new Set(defaultConds.filter(c => CONDITIONS.includes(c)));
    const qualChecked  = new Set(defaultQuals.filter(q => QUALS.includes(q)));

    const totalCards = extra.totalCards ?? firstCart.length;
    let userCart         = defaultCart;
    let currentOverrides = extra.initialOverrides || [];
    const backendLogs    = [];
    let isCalc           = false;
    let debounceId       = null;

    if (extra.onLog) extra.onLog(text => { backendLogs.push(text); renderNotice(); });

    const summaries = [
      { ...buildSummary(firstCart), cards: totalCards },
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
    desc.textContent = 'Select a cart below, or adjust filters to rebuild the optimized cart.';
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
      b.addEventListener('click', () => { if (zone === 0) { selectedCart = i; renderAll(); } });
      b.addEventListener('mouseenter', () => { if (zone === 0) { selectedCart = i; renderAll(); } });
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

    // ── Notice box ─────────────────────────────────────────────────────────
    const noticeBox = document.createElement('div');
    noticeBox.className = 'notice-box';
    const noticeTitle = document.createElement('div');
    noticeTitle.className = 'notice-title';
    noticeTitle.textContent = 'Notices';
    noticeBox.appendChild(noticeTitle);
    screen.appendChild(noticeBox);

    // ── Action bar ─────────────────────────────────────────────────────────
    const actionsEl = document.createElement('div');
    actionsEl.className = 'optimizer-actions';
    actionsEl.innerHTML = `
      <span class="hint"><span style="color:var(--secondary)">[Enter]</span> Confirm cart</span>
      <span class="hint"><span style="color:var(--secondary)">[Tab]</span> Switch zone</span>
      <span class="hint"><span style="color:var(--secondary)">[R]</span> Restart</span>
      <span class="hint"><span style="color:var(--secondary)">[Esc]</span> Home</span>
    `;
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
          scheduleOptimize();
          renderAll();
        });
        el.addEventListener('mouseenter', () => { filterRows[col] = idx; renderFilterBox(col); });
        box.appendChild(el);
      });
    }

    function renderNotice() {
      while (noticeBox.children.length > 1) noticeBox.removeChild(noticeBox.lastChild);
      for (const o of currentOverrides) {
        const el = document.createElement('div');
        el.className = 'notice-warn';
        el.textContent = `⚠ ${o.name}: ${o.applied}`;
        noticeBox.appendChild(el);
      }
      for (const line of backendLogs) {
        const el = document.createElement('div');
        el.className = 'notice-debug';
        el.textContent = line;
        noticeBox.appendChild(el);
      }
    }

    function renderHint() {
      hintEl.textContent = zone === 0
        ? 'CARTS  ←/→ navigate  •  Enter confirm  •  Tab: go to filters  •  R restart  •  Esc home'
        : 'FILTERS  ←/→ columns  •  ↑/↓ navigate  •  Space toggle  •  Tab: go to carts  •  R restart  •  Esc home';
    }

    function renderAll() {
      renderSavings();
      renderCartBox(0); renderCartBox(1);
      renderFilterBox(0); renderFilterBox(1);
      renderNotice();
      renderHint();
    }

    // ── Debounced re-optimization ──────────────────────────────────────────
    function scheduleOptimize() {
      if (extra.onFiltersChange) extra.onFiltersChange({ conditions: [...condChecked], sellerQuals: [...qualChecked] });
      if (debounceId) clearTimeout(debounceId);
      isCalc = true; startSpinner();
      debounceId = setTimeout(async () => {
        try {
          const result = await call('optimize_filtered', {
            conditions:  [...condChecked],
            sellerQuals: [...qualChecked],
          });
          userCart         = result.cart;
          currentOverrides = result.overrides || [];
          summaries[1]     = buildSummary(userCart);
        } catch (_) {}
        finally {
          isCalc = false; stopSpinner();
          renderAll();
        }
      }, 300);
    }

    // ── Keyboard handling ──────────────────────────────────────────────────
    _onKey(e => {
      if (e.key === 'Tab') {
        e.preventDefault();
        zone = 1 - zone;
        renderAll();
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
        scheduleOptimize();
        renderFilterBox(filterCol);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (selectedCart === 1 && isCalc) return;
        const carts = [firstCart, userCart];
        if (spinTimer) clearInterval(spinTimer);
        if (debounceId) clearTimeout(debounceId);
        resolve({
          action: 'confirm',
          cart: carts[selectedCart],
          cartTitle: CART_TITLES[selectedCart],
          summary: summaries[selectedCart],
        });
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        if (spinTimer) clearInterval(spinTimer);
        if (debounceId) clearTimeout(debounceId);
        resolve({ action: 'restart' });
      } else if (e.key === 'Escape') {
        e.preventDefault();
        if (spinTimer) clearInterval(spinTimer);
        if (debounceId) clearTimeout(debounceId);
        resolve({ action: 'home' });
      }
    });

    if (extra.onFiltersChange) extra.onFiltersChange({ conditions: [...condChecked], sellerQuals: [...qualChecked] });
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
