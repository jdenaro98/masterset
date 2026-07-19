---
name: frontend
description: Working on the masterset web frontend — the vanilla-JS Vite app that renders the terminal-style TUI (splash, game/set/card pickers, dynamic optimizer, cart handoff) and talks to the backend over a WebSocket. Use when editing frontend/src/*.js, style.css, the Vite config, or debugging the UI flow, theming, or the cart bookmarklet.
---

# masterset frontend

A single-page, **vanilla JavaScript** app (no framework) that renders a terminal/TUI aesthetic in the browser. It walks the user through a linear flow — splash → game → set → card selection → dynamic optimizer → cart — driving a Python backend over one WebSocket. Deployed as a static site to GitHub Pages; the backend is hosted separately on Railway.

## Stack & tools
- **Vanilla JS, ES modules**, no framework, no runtime deps. DOM built imperatively (`innerHTML` + `document.createElement`), keyboard-driven.
- **Vite 6** — dev server (`:5173`), build, HMR. Config: [frontend/vite.config.js](../../../frontend/vite.config.js).
- **CSS** — one hand-written [frontend/src/style.css](../../../frontend/src/style.css) themed via CSS custom properties; `<canvas>` used for the animated splash art. Font: Fira Code (Google Fonts, loaded in [index.html](../../../frontend/index.html)).
- **ESLint 9** (flat config, `eslint.config.js`) — the only frontend check in CI. Browser globals; `_`-prefixed vars/args/caught-errors are ignored-unused; empty catch allowed. Run `npm run lint` in `frontend/`.
- No test suite, no TypeScript.

## Files
- [frontend/src/app.js](../../../frontend/src/app.js) — flow orchestration. `boot()` → `mainLoop()` → `runCardSelection()`. Owns the state machine and sessionStorage-backed resume-on-refresh. Calls backend methods and wires progress-event handlers to UI callbacks.
- [frontend/src/ui.js](../../../frontend/src/ui.js) — all screen/widget rendering (~1600 lines). Each `show*` function paints a screen and returns a Promise that resolves on the user's choice, or an object of callbacks for streaming screens. This is where nearly all DOM/keyboard/animation code lives.
- [frontend/src/api.js](../../../frontend/src/api.js) — WebSocket client. `connect()`, `call(method, params)→Promise`, `on/off(type, handler)` for pushed events. Exposes `ART_BASE` and `BACKEND_WS_URL`.
- [frontend/src/style.css](../../../frontend/src/style.css) — theme variables + all styling.

## Backend communication ([api.js](../../../frontend/src/api.js))
One WebSocket, JSON-RPC-ish:
- `call(method, params)` sends `{id, method, params}` and resolves with the matching `{id, result}` (or rejects on `{id, error}`). Pending calls tracked by id in a `Map`.
- Server also pushes typed events with no id: `{type: "progress"|"probe_progress"|"card_page_progress"|"cart_progress"|"backend_log", ...}`. Subscribe with `on(type, fn)`; **always** `off()` in a `finally` after the awaited `call` resolves (see the probe/listing loops in app.js).
- URL selection: dev uses relative `/ws` proxied by Vite; prod uses `VITE_BACKEND_URL` (set at build time) rewritten `http→ws`. `BACKEND_WS_URL` is the absolute `wss://` URL the cart bookmarklet needs because it runs on tcgplayer.com, outside our origin.

## The flow (app.js state machine)
1. **Boot** — `connect()`, then `get_theme` (random Pokémon ASCII + dominant RGB colors) → `applyTheme` + `runSplash` canvas animation.
2. **Home** (`showMainScreen`) — launch or restart. Being here means "no flow in progress," so it's the single choke point that clears flow state.
3. **Game** → `fetch_categories`, `showGridSelectWithSearch`.
4. **Set** → `check_filter_cache`; if uncached, `fetch_sets` + stream `filter_sets` probe progress into `showFilterProgress`; then `showAutocomplete` (with a force-refresh option).
5. **Cards** → `fetch_cards`, `showMultiSelect`. Multiple sets can be accumulated.
6. **Scrape** → `fetch_listings`, streaming `progress`/`card_page_progress` into `showProgress`.
7. **Dynamic optimizer** (`showDynamicOptimizer`) — the core screen. Shows the baseline "first listings" cart vs. the seller-bundled "dynamic" cart, lets the user toggle condition/seller-qual filters (re-calling `optimize_filtered`), highlights the cheaper cart green, and surfaces `overrides` (why a filter was relaxed for a card).
8. **Cart** → `create_cart` (streams `cart_progress`), then `showCartResult` builds a **bookmarklet** the user saves and clicks on tcgplayer.com to batch-add items.

## UI conventions ([ui.js](../../../frontend/src/ui.js))
- Every screen is a `show*` function; interactive ones return a Promise resolving to the user's selection, streaming ones return `{onComplete, onDebug, ...}` callbacks.
- Keyboard-first: sentinel return values like `'__restart__'`, `'__exit__'`, `'__refresh__'` flow back up to `app.js` to control navigation. `waitForKey(msg)` for simple prompts.
- Helpers: `_makeScreen`, `_onKey`, `_onResize`, `_responsiveCols` (grid reflow), `parseArtColors` (parses ANSI-escape RGB from the backend art), canvas splash drawing.
- Theming: `applyTheme(primary, secondary, accent)` sets CSS custom properties from the backend's per-Pokémon RGB triples. Art assets load from `ART_BASE` (`/art` in dev, absolute backend URL in prod).

## Resume-on-refresh (app.js)
Mid-flow state is snapshotted to `sessionStorage` (`masterset:flowState`) at checkpoints (`step: 'game'|'set'|'optimizer'`) so a browser refresh drops the user back where they were instead of replaying the splash. The home screen always clears it. `runCardSelection(resume)` short-circuits already-completed steps. Listings are re-fetchable via `check_listings_cache` if the backend restarted.

## Run & deploy
- Dev: `npm run dev` from repo root runs Vite (`:5173`) + backend together. Vite proxies `/ws` and `/art` to `https://localhost:8000` with `secure:false` (accepts the backend's self-signed dev cert). Open `localhost:5173`; for cart testing also open `https://localhost:8000` once to trust the cert.
- Build: `vite build` → `../dist`. CI deploy ([.github/workflows/deploy.yml](../../../.github/workflows/deploy.yml)) builds with `--base=/masterset/` and `VITE_BACKEND_URL`, publishes `dist/` to GitHub Pages on push to `main`. Prod URL: `https://jdenaro98.github.io/masterset/`.
