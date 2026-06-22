'use strict';

const { app, BrowserWindow, ipcMain } = require('electron');
const pty  = require('node-pty');
const path = require('path');
const fs   = require('fs');
const { execFileSync } = require('child_process');

function logFile() {
  try {
    return path.join(app.getPath('userData'), 'masterset-startup.log');
  } catch {
    return null;
  }
}

function writeLog(msg) {
  const f = logFile();
  if (f) {
    try { fs.appendFileSync(f, `[${new Date().toISOString()}] ${msg}\n`); } catch {}
  }
}

// On Windows, Electron.exe is compiled as a /SUBSYSTEM:WINDOWS GUI application.
// When node-pty spawns it via ConPTY the pseudoconsole handles don't connect to
// the GUI exe's stdio, so the process runs silently. Use a bundled node.exe
// (a /SUBSYSTEM:CONSOLE app) instead. On macOS/Linux the Electron binary works fine.
function resolveNodeBin() {
  if (app.isPackaged) {
    if (process.platform === 'win32') {
      const bundled = path.join(process.resourcesPath, 'bin', 'node.exe');
      if (fs.existsSync(bundled)) return bundled;
    }
    return process.execPath;
  }
  if (process.platform === 'win32') return 'node';
  for (const sh of ['/bin/bash', '/bin/zsh', '/bin/sh']) {
    try {
      return execFileSync(sh, ['-l', '-c', 'which node'], { encoding: 'utf8' }).trim();
    } catch {}
  }
  return 'node';
}
const NODE_BIN = resolveNodeBin();
// Only needed when we're running the Electron binary itself as Node
const NEEDS_ELECTRON_AS_NODE = app.isPackaged && process.platform !== 'win32';

let win, ptyProcess;

app.setName('masterset');

if (app.dock) {
  app.dock.setIcon(path.join(__dirname, 'build', 'icons', 'png', '512x512.png'));
}

app.whenReady().then(() => {
  win = new BrowserWindow({
    width:           1300,
    height:          860,
    backgroundColor: '#000000',
    autoHideMenuBar: true,
    title:           'masterset',
    icon:            path.join(__dirname, 'build', 'icons', 'png', '512x512.png'),
    webPreferences: {
      nodeIntegration:  true,
      contextIsolation: false,
    },
  });

  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  win.webContents.on('did-finish-load', () => {
    // Pass packaging info as env vars — the child process runs via ELECTRON_RUN_AS_NODE
    // so it has no access to Electron APIs like app.isPackaged or process.resourcesPath.
    const env = {
      ...process.env,
      COLORTERM:              'truecolor',
      TERM:                   'xterm-256color',
      BLESSED_FORCE_MODES:    'SGRMOUSE=1,ALLMOTION=1,VT200MOUSE=1,CELLMOTION=1',
      MASTERSET_PACKAGED:    app.isPackaged ? '1' : '',
      MASTERSET_RESOURCES:   process.resourcesPath,
      MASTERSET_USER_DATA:   app.getPath('userData'),
    };
    if (NEEDS_ELECTRON_AS_NODE) env.ELECTRON_RUN_AS_NODE = '1';

    writeLog(`Spawning PTY: ${NODE_BIN} ${path.join(__dirname, 'main.js')}`);
    writeLog(`isPackaged=${app.isPackaged} platform=${process.platform} arch=${process.arch}`);
    writeLog(`resourcesPath=${process.resourcesPath}`);

    try {
      ptyProcess = pty.spawn(NODE_BIN, [path.join(__dirname, 'main.js')], {
        name: 'xterm-256color',
        cols: 160,
        rows: 50,
        cwd:  __dirname,
        env,
      });
    } catch (err) {
      writeLog(`pty.spawn failed: ${err.stack || err.message}`);
      win.webContents.send('pty-data',
        `\r\n\x1b[31m[masterset] Failed to start terminal process:\x1b[0m\r\n${err.message}\r\n\r\n` +
        `\x1b[33mLog file: ${logFile() || '(unavailable)'}\x1b[0m\r\n`
      );
      return;
    }

    ptyProcess.onData(data => win.webContents.send('pty-data', data));
    ptyProcess.onExit(({ exitCode }) => {
      writeLog(`PTY process exited with code ${exitCode}`);
      app.quit();
    });
  });

  win.on('closed', () => {
    if (ptyProcess) ptyProcess.kill();
    win = null;
  });
});

ipcMain.on('pty-input',    (_, data)          => ptyProcess && ptyProcess.write(data));
ipcMain.on('pty-resize',   (_, { cols, rows }) => ptyProcess && ptyProcess.resize(cols, rows));
ipcMain.on('fit-to-terminal', (_, { width, height }) => win && win.setContentSize(width, height));

ipcMain.on('open-bmc-donate', (_, { amount }) => {
  let bin, args;
  if (app.isPackaged) {
    const ext = process.platform === 'win32' ? '.exe' : '';
    bin  = path.join(process.resourcesPath, 'backend_server', `backend_server${ext}`);
    args = [`--bmc-donate=${amount}`];
  } else {
    const venvPy = process.platform === 'win32'
      ? path.join(__dirname, 'venv', 'Scripts', 'python.exe')
      : path.join(__dirname, 'venv', 'bin', 'python3');
    bin  = fs.existsSync(venvPy) ? venvPy : 'python3';
    args = [path.join(__dirname, 'backend', 'server.py'), `--bmc-donate=${amount}`];
  }
  const { spawn } = require('child_process');
  spawn(bin, args, {
    stdio:    'ignore',
    env:      { ...process.env, MASTERSET_USER_DATA: app.getPath('userData') },
    detached: true,
  }).unref();
});

app.on('window-all-closed', () => {
  if (ptyProcess) ptyProcess.kill();
  app.quit();
});
