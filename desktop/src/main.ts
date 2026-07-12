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

if (process.platform === 'win32' && started) {
  app.quit();
}

if (process.platform === 'linux' && !app.isPackaged) {
  app.disableHardwareAcceleration();
}

process.on('uncaughtException', (error) => {
  console.error('[desktop] uncaught exception', error);
});

process.on('unhandledRejection', (reason) => {
  console.error('[desktop] unhandled rejection', reason);
});

let mainWindow: BrowserWindow | null = null;

function createWindow(): void {
  console.log('[desktop] creating main window');

  mainWindow = new BrowserWindow({
    width: 1100,
    height: 780,
    minWidth: 860,
    minHeight: 640,
    show: false,
    backgroundColor: '#07090f',
    title: 'MockMate',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => {
    console.log('[desktop] main window ready');
    mainWindow?.show();
  });

  mainWindow.on('closed', () => {
    console.log('[desktop] main window closed');
    mainWindow = null;
  });

  mainWindow.webContents.on('did-fail-load', (_event, code, description, url) => {
    console.error('[desktop] renderer failed to load', { code, description, url });
  });

  mainWindow.webContents.on('preload-error', (_event, preloadPath, error) => {
    console.error('[desktop] preload failed', { preloadPath, error });
  });

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error('[desktop] renderer process exited', details);
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.webContents.on('will-navigate', (event, url) => {
    const devServerAllowed = MAIN_WINDOW_VITE_DEV_SERVER_URL
      ? url.startsWith(MAIN_WINDOW_VITE_DEV_SERVER_URL)
      : false;
    const allowed =
      url.startsWith('file://') ||
      url.startsWith('http://127.0.0.1:3000') ||
      url.startsWith('http://localhost:3000') ||
      devServerAllowed;
    if (!allowed) event.preventDefault();
  });

  const loadWindow = MAIN_WINDOW_VITE_DEV_SERVER_URL
    ? mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL)
    : mainWindow.loadFile(path.join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`));

  void loadWindow.catch((error) => {
    console.error('[desktop] failed to open setup UI', error);
  });
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

app.on('render-process-gone', (_event, webContents, details) => {
  console.error('[desktop] application renderer exited', {
    id: webContents.id,
    details,
  });
});

app.on('child-process-gone', (_event, details) => {
  console.error('[desktop] Electron child process exited', details);
});

void app
  .whenReady()
  .then(() => {
    console.log('[desktop] Electron ready');
    registerIpc();
    createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  })
  .catch((error) => {
    console.error('[desktop] application failed during startup', error);
  });

let shutdownStarted = false;
app.on('before-quit', (event) => {
  if (shutdownStarted) return;
  event.preventDefault();
  shutdownStarted = true;
  console.log('[desktop] stopping local services');
  void stopServices().finally(() => app.quit());
});

app.on('window-all-closed', () => {
  console.log('[desktop] all windows closed');
  if (process.platform !== 'darwin') app.quit();
});
