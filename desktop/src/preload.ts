import { contextBridge, ipcRenderer } from 'electron';
import type { MockMateDesktopApi, ServiceEvent } from './types';

const api: MockMateDesktopApi = {
  getCredentialStatus: () => ipcRenderer.invoke('credentials:status'),
  getSavedCredentials: () => ipcRenderer.invoke('credentials:get'),
  saveCredentials: (credentials, remember) =>
    ipcRenderer.invoke('credentials:save', credentials, remember),
  clearCredentials: () => ipcRenderer.invoke('credentials:clear'),
  testCredentials: (credentials) => ipcRenderer.invoke('credentials:test', credentials),
  startMockMate: (credentials, remember) =>
    ipcRenderer.invoke('services:start', credentials, remember),
  stopMockMate: () => ipcRenderer.invoke('services:stop'),
  onServiceEvent: (listener) => {
    const handler = (_event: Electron.IpcRendererEvent, payload: ServiceEvent) => listener(payload);
    ipcRenderer.on('services:event', handler);
    return () => ipcRenderer.removeListener('services:event', handler);
  },
};

contextBridge.exposeInMainWorld('mockMateDesktop', api);
