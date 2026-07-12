import { app, BrowserWindow, ipcMain, shell } from 'electron';
import path from 'node:path';
import started from 'electron-squirrel-startup';
import {
  clearCredentials,
  credentialStatus,
  loadCredentials,
  saveCredentials,
} from './credential-store';
import { testCredentials } from './provider-tests';
import { startServices, stopServices } from './service-manager';
import type { MockMateCredentials } from './types';

declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
declare const MAIN_WINDOW_VITE_NAME: string;

if (started) app.quit();

let mainWindow: BrowserWindow | null = null;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 780,
    minWidth: 860,
    minHeight: 640,
    backgroundColor: '#07090f',
    title: 'MockMate',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('will-navigate', (event, url) => {
    const allowed =
      url.startsWith('file://') ||
      url.startsWith('http://127.0.0.1:3000') ||
      url.startsWith('http://localhost:3000');
    if (!allowed) event.preventDefault();
  });

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    void mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    void mainWindow.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`));
  }
}

function registerIpc(): void {
  ipcMain.handle('credentials:status', () => credentialStatus());
  ipcMain.handle('credentials:get', () => loadCredentials());
  ipcMain.handle(
    'credentials:save',
    (_event, credentials: MockMateCredentials, remember: boolean) =>
      saveCredentials(credentials, remember),
  );
  ipcMain.handle('credentials:clear', () => clearCredentials());
  ipcMain.handle('credentials:test', (_event, credentials: MockMateCredentials) =>
    testCredentials(credentials),
  );
  ipcMain.handle(
    'services:start',
    async (_event, credentials: MockMateCredentials, remember: boolean) => {
      await saveCredentials(credentials, remember);
      const result = await startServices(credentials);
      await mainWindow?.loadURL(result.frontendUrl);
      return result;
    },
  );
  ipcMain.handle('services:stop', () => stopServices());
}

app.whenReady().then(() => {
  registerIpc();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

let shutdownStarted = false;
app.on('before-quit', (event) => {
  if (shutdownStarted) return;
  event.preventDefault();
  shutdownStarted = true;
  void stopServices().finally(() => app.quit());
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
