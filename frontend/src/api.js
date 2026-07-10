'use strict';
/**
 * WebSocket client — same JSON-RPC protocol as the old stdin/stdout IPC.
 *
 * call(method, params)  → Promise<result>
 * on(type, handler)     → subscribe to server-pushed events  (e.g. "progress")
 * off(type, handler)    → unsubscribe
 * connect()             → open WebSocket, returns Promise that resolves on open
 */

// In production VITE_BACKEND_URL is set to the hosted backend origin.
// In dev it is empty and Vite's proxy handles /ws and /art.
const BACKEND = import.meta.env.VITE_BACKEND_URL || '';

const WS_URL = BACKEND
  ? `${BACKEND.replace(/^http/, 'ws')}/ws`
  : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;

export const ART_BASE = BACKEND ? `${BACKEND}/art` : '/art';

// Absolute backend WebSocket URL. Needed by things that run outside our own
// page (the cart bookmarklet executes on tcgplayer.com) where relative URLs
// and the dev-server proxy don't apply. TCGPlayer's CSP blocks fetch() to
// arbitrary origins but allows unrestricted `wss:`, so the bookmarklet talks
// to the backend over this same WebSocket channel rather than plain REST.
export const BACKEND_WS_URL = BACKEND
  ? `${BACKEND.replace(/^http/, 'ws')}/ws`
  : `wss://${location.hostname}:8000/ws`;

let ws        = null;
let nextId    = 1;
const pending   = new Map();   // id → { resolve, reject }
const listeners = new Map();   // type → [handler, ...]

export function connect() {
  return new Promise((resolve, reject) => {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => resolve();

    ws.onerror = (e) => reject(new Error(`WebSocket error: ${e.message || 'failed to connect'}`));

    ws.onmessage = ({ data }) => {
      let msg;
      try { msg = JSON.parse(data); } catch { return; }

      if (msg.type) {
        for (const h of (listeners.get(msg.type) || [])) h(msg);
      } else if (msg.id != null) {
        const p = pending.get(msg.id);
        if (!p) return;
        pending.delete(msg.id);
        if (msg.error) p.reject(new Error(msg.error));
        else           p.resolve(msg.result);
      }
    };

    ws.onclose = () => {
      for (const p of pending.values()) p.reject(new Error('Connection closed'));
      pending.clear();
    };
  });
}

export function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

export function on(type, handler) {
  if (!listeners.has(type)) listeners.set(type, []);
  listeners.get(type).push(handler);
}

export function off(type, handler) {
  const hs = listeners.get(type);
  if (!hs) return;
  const i = hs.indexOf(handler);
  if (i >= 0) hs.splice(i, 1);
}
