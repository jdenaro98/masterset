'use strict';

const { app, BrowserWindow, ipcMain } = require('electron');
const pty  = require('node-pty');
const path = require('path');

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
    ptyProcess = pty.spawn('node', [path.join(__dirname, 'main.js')], {
      name: 'xterm-256color',
      cols: 160,
      rows: 50,
      cwd:  __dirname,
      env:  { ...process.env, COLORTERM: 'truecolor', TERM: 'xterm-256color' },
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
