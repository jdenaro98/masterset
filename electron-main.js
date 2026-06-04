'use strict';

const { app, BrowserWindow, ipcMain } = require('electron');
const pty  = require('node-pty');
const path = require('path');
const { execFileSync } = require('child_process');

function resolveNodeBin() {
  // In packaged app, use the bundled Electron binary as a Node runtime
  if (app.isPackaged) return process.execPath;
  for (const sh of ['/bin/bash', '/bin/zsh', '/bin/sh']) {
    try {
      return execFileSync(sh, ['-l', '-c', 'which node'], { encoding: 'utf8' }).trim();
    } catch {}
  }
  return 'node';
}
const NODE_BIN = resolveNodeBin();

let win, ptyProcess;

app.whenReady().then(() => {
  win = new BrowserWindow({
    width:           1300,
    height:          860,
    backgroundColor: '#000000',
    autoHideMenuBar: true,
    title:           'TCGScraper',
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
      TCGSCRAPER_PACKAGED:    app.isPackaged ? '1' : '',
      TCGSCRAPER_RESOURCES:   process.resourcesPath,
      TCGSCRAPER_USER_DATA:   app.getPath('userData'),
    };
    if (app.isPackaged) env.ELECTRON_RUN_AS_NODE = '1';

    ptyProcess = pty.spawn(NODE_BIN, [path.join(__dirname, 'main.js')], {
      name: 'xterm-256color',
      cols: 160,
      rows: 50,
      cwd:  __dirname,
      env,
    });

    ptyProcess.onData(data => win.webContents.send('pty-data', data));
    ptyProcess.onExit(() => app.quit());
  });

  win.on('closed', () => {
    if (ptyProcess) ptyProcess.kill();
    win = null;
  });
});

ipcMain.on('pty-input',    (_, data)          => ptyProcess && ptyProcess.write(data));
ipcMain.on('pty-resize',   (_, { cols, rows }) => ptyProcess && ptyProcess.resize(cols, rows));
ipcMain.on('fit-to-terminal', (_, { width, height }) => win && win.setContentSize(width, height));

app.on('window-all-closed', () => {
  if (ptyProcess) ptyProcess.kill();
  app.quit();
});
