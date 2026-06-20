'use strict';
/**
 * Manages the Python backend child process.
 *
 * call(method, params) → Promise<result>
 * on(eventType, handler) → subscribe to pushed events (e.g. "progress")
 */

const { spawn }   = require('child_process');
const path        = require('path');
const readline    = require('readline');

let pyProc = null;
let nextId = 1;
const pending   = new Map();   // id → { resolve, reject }
const listeners = new Map();   // type → [handler, ...]

function spawnBackend() {
  const isPackaged = process.env.MASTERSET_PACKAGED === '1';
  const root = path.resolve(__dirname, '..');

  let pythonExe, args, cwd;

  if (isPackaged) {
    // Use the PyInstaller-bundled binary placed in extraResources/backend_server/
    const ext = process.platform === 'win32' ? '.exe' : '';
    pythonExe = path.join(process.env.MASTERSET_RESOURCES, 'backend_server', `backend_server${ext}`);
    args = [];
    cwd  = process.env.MASTERSET_USER_DATA || root;
  } else {
    // Dev: prefer venv Python, fall back to system python3
    const venvPy = process.platform === 'win32'
      ? path.join(root, 'venv', 'Scripts', 'python.exe')
      : path.join(root, 'venv', 'bin', 'python3');
    pythonExe = require('fs').existsSync(venvPy) ? venvPy : 'python3';
    args = [path.join(root, 'backend', 'server.py')];
    cwd  = root;
  }

  pyProc = spawn(pythonExe, args, {
    stdio: ['pipe', 'pipe', 'pipe'],
    cwd,
    env: {
      ...process.env,
      MASTERSET_USER_DATA: process.env.MASTERSET_USER_DATA || root,
    },
  });

  const rl = readline.createInterface({ input: pyProc.stdout });
  rl.on('line', line => {
    if (!line.trim()) return;
    let msg;
    try { msg = JSON.parse(line); } catch { return; }

    if (msg.type) {
      // Pushed event (e.g. progress)
      const handlers = listeners.get(msg.type) || [];
      handlers.forEach(h => h(msg));
    } else if (msg.id != null) {
      const p = pending.get(msg.id);
      if (!p) return;
      pending.delete(msg.id);
      if (msg.error) p.reject(new Error(msg.error));
      else           p.resolve(msg.result);
    }
  });

  let stderrBuf = '';
  pyProc.stderr.on('data', d => {
    stderrBuf += d.toString();
    const lines = stderrBuf.split('\n');
    stderrBuf = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      // Drop Playwright/Chromium internal noise (e.g. "node: 75517")
      if (/^node: \d+$/.test(line.trim())) continue;
      const handlers = listeners.get('backend_log') || [];
      handlers.forEach(h => h({ type: 'backend_log', text: line }));
    }
  });

  pyProc.on('exit', code => {
    process.stderr.write(`[ipc] backend exited (code ${code})\n`);
  });
}

function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id  = nextId++;
    const msg = JSON.stringify({ id, method, params }) + '\n';
    pending.set(id, { resolve, reject });
    pyProc.stdin.write(msg);
  });
}

function on(eventType, handler) {
  if (!listeners.has(eventType)) listeners.set(eventType, []);
  listeners.get(eventType).push(handler);
}

function kill() {
  if (pyProc) pyProc.kill();
}

module.exports = { spawnBackend, call, on, kill };
