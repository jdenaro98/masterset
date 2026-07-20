---
name: frontend
description: Working on the masterset web frontend — the vanilla-JS Vite app that renders the terminal-style TUI (splash, game/set/card pickers, the binder page, cart handoff), the persistent binder cart, and the home/binder nav chrome, all talking to the backend over a WebSocket. Use when editing frontend/src/*.js, style.css, the Vite config, or debugging the UI flow, theming, or the cart bookmarklet.
---

# masterset frontend

A single-page, **vanilla JavaScript** app (no framework) that renders a terminal/TUI aesthetic in the browser. It walks the user through a flow — splash → game → set → card selection → **binder** → cart — driving a Python backend over one WebSocket. Cards picked from any number of sets/games accumulate into a browser-persistent **binder** (the app's internal cart); the binder page prices/optimizes the whole thing. Deployed as a static site to GitHub Pages; the backend is hosted separately on Railway.

## Stack & tools
- **Vanilla JS, ES modules**, no framework, no runtime deps. DOM built imperatively (`innerHTML` + `document.createElement`), keyboard-driven.
- **Vite 6** — dev server (`:5173`), build, HMR. Config: [frontend/vite.config.js](../../../frontend/vite.config.js).
- **CSS** — one hand-written [frontend/src/style.css](../../../frontend/src/style.css) themed via CSS custom properties; `<canvas>` used for the animated splash art. Font: Fira Code (Google Fonts, loaded in [index.html](../../../frontend/index.html)).
- **ESLint 9** (flat config, `eslint.config.js`) — the only frontend check in CI. Browser globals; `_`-prefixed vars/args/caught-errors are ignored-unused; empty catch allowed. Run `npm run lint` in `frontend/`.
- No test suite, no TypeScript.

## Files
- [frontend/src/app.js](../../../frontend/src/app.js) — flow orchestration. `boot()` → `mainLoop()` → `runCardSelection()` / `runBinder()`. Owns the state machine, the `NavController` (home/binder chrome), and sessionStorage-backed resume-on-refresh. Calls backend methods and wires progress-event handlers to UI callbacks.
- [frontend/src/ui.js](../../../frontend/src/ui.js) — all screen/widget rendering (~1700 lines). Each `show*` function paints a screen and returns a Promise that resolves on the user's choice, or an object of callbacks for streaming screens. This is where nearly all DOM/keyboard/animation code lives. `showBinder` is the core screen.
- [frontend/src/binder.js](../../../frontend/src/binder.js) — the persistent binder model. localStorage-backed (`masterset:binder`); `addCards`/`removeCard`/`clearBinder`/`getCards`/`getFilters`/`saveBinderFilters`/`toTask`. `cardId(productId, printing)` = `` `${productId}:${printing||''}` `` — the stable card identity shared with the backend cache.
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
5. **Cards** → `fetch_cards`, `showMultiSelect`, then an **"Add N cards to your binder?"** confirm. **Yes** → `binder.addCards(...)` and `runCardSelection` returns `'binder'`; **No** → re-show the picker with the selection intact. This is where `runCardSelection` now ends (the scrape/optimize moved into `runBinder`).
6. **Binder** (`runBinder` → `showBinder`) — the core landing screen. On entry it scrapes only the binder cards not already cached (delta; `check_listings_cache` → `fetch_listings` with `merge:true`, streaming `progress` into `showProgress`), then `get_filter_options`/`optimize_filtered` **scoped to the binder's `cardIds`**. The screen shows the baseline "first listings" cart vs. the seller-bundled "dynamic" cart, a live 3-col card list (name · set · price · delete), condition/seller-qual filters (re-optimizing in place on toggle **or per-card delete**), and moves the filter-relaxation `overrides` behind a **Notices** badge button. Actions: confirm cart, **Refresh prices** (re-scrape all), **Clear binder**.
7. **Cart** → `create_cart` (streams `cart_progress`), then `showCartResult` builds a **bookmarklet** the user saves and clicks on tcgplayer.com to batch-add items. The binder is **not** cleared after handoff, so the user can return to it.

## Binder & nav chrome
- **Binder** ([binder.js](../../../frontend/src/binder.js)) is the source of truth for which cards are being optimized — a localStorage list of card descriptors, deduped by `cardId`, surviving refresh/restart. The backend's in-memory listing cache is a rebuildable derivative keyed by the same `cardId`. `runBinder` is a loop: (re)optimize + `showBinder`, reacting to its resolved `action` (`confirm`/`home`/`refresh`/`clear`/`empty`) or a `{__nav}` sentinel. Empty binder (cold open, delete-all, last-card delete) routes to `showBinderEmpty`.
- **Nav chrome** — persistent `#nav-chrome` (a child of `#app`, so it survives `_makeScreen` swaps; sits above screens, below modals) holds a **Home** icon (top-left, hidden on the home screen) and a **Binder** icon (top-right with a count badge, hidden on the binder page). Owned by the `NavController` in app.js: `configure({home, binder, guard})` sets visibility + guard, `updateBadge()` refreshes the count. A click calls `triggerScreenNav(target)` (ui.js), which resolves the **active screen's** promise with `{__nav:'home'|'binder'}`; app.js maps that to a flow outcome. During the selection flow `guard:true` first pops a confirm (using `pauseScreenKeys`/`resumeScreenKeys` so the screen underneath doesn't also act on Enter).

## UI conventions ([ui.js](../../../frontend/src/ui.js))
- Every screen is a `show*` function; interactive ones return a Promise resolving to the user's selection, streaming ones return `{onComplete, onDebug, ...}` callbacks.
- Keyboard-first: sentinel return values like `'__restart__'`, `'__exit__'`, `'__refresh__'` flow back up to `app.js` to control navigation. `waitForKey(msg)` for simple prompts.
- Global nav interruption: an interruptible screen calls `_navScreen(resolve)` after `_makeScreen()` to register its resolver; `triggerScreenNav(target)` (called by the NavController on an icon click) resolves it with `{__nav}`. `_makeScreen` auto-clears the previous screen's key/resize listeners, so an abandoned screen promise is inert. `pauseScreenKeys`/`resumeScreenKeys` detach a screen's key handlers while a modal is open.
- Helpers: `_makeScreen`, `_onKey`, `_onResize`, `_responsiveCols` (grid reflow), `parseArtColors` (parses ANSI-escape RGB from the backend art), canvas splash drawing.
- Theming: `applyTheme(primary, secondary, accent)` sets CSS custom properties from the backend's per-Pokémon RGB triples. Art assets load from `ART_BASE` (`/art` in dev, absolute backend URL in prod).

## Persistence: two stores (app.js + binder.js)
- **`sessionStorage` (`masterset:flowState`)** — tab-scoped, mid-flow resume. Checkpoints `step: 'game'|'set'|'cards'|'binder'`; a refresh drops the user back where they were instead of replaying the splash. `boot()` routes `step:'binder'` to `runBinder`, everything else to `runCardSelection(resume)` (which short-circuits completed steps). The home screen always clears it.
- **`localStorage` (`masterset:binder`)** — the durable binder (survives tab close / restart), see [binder.js](../../../frontend/src/binder.js). This is what makes the binder an "anonymous cart." Backend listings are re-fetchable via `check_listings_cache` (delta) if the backend restarted.

## Run & deploy
- Dev: `npm run dev` from repo root runs Vite (`:5173`) + backend together. Vite proxies `/ws` and `/art` to `https://localhost:8000` with `secure:false` (accepts the backend's self-signed dev cert). Open `localhost:5173`; for cart testing also open `https://localhost:8000` once to trust the cert.
- Build: `vite build` → `../dist`. CI deploy ([.github/workflows/deploy.yml](../../../.github/workflows/deploy.yml)) builds with `--base=/masterset/` and `VITE_BACKEND_URL`, publishes `dist/` to GitHub Pages on push to `main`. Prod URL: `https://jdenaro98.github.io/masterset/`.
