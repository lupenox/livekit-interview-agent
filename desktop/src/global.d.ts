import type { MockMateDesktopApi } from './types';

declare global {
  interface Window {
    mockMateDesktop: MockMateDesktopApi;
  }
}

export {};
