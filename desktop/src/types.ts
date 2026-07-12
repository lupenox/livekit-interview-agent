export type ProviderName = 'LiveKit' | 'Groq' | 'Deepgram' | 'ElevenLabs';

export type MockMateCredentials = {
  livekitUrl: string;
  livekitApiKey: string;
  livekitApiSecret: string;
  groqApiKey: string;
  deepgramApiKey: string;
  elevenlabsApiKey: string;
};

export type CredentialStatus = {
  saved: boolean;
  encryptionAvailable: boolean;
};

export type ProviderTest = {
  provider: ProviderName;
  ok: boolean;
  message: string;
};

export type StartResult = {
  frontendUrl: string;
};

export type ServiceEvent = {
  service: 'agent' | 'frontend';
  stream: 'stdout' | 'stderr' | 'status';
  message: string;
};

export type MockMateDesktopApi = {
  getCredentialStatus: () => Promise<CredentialStatus>;
  getSavedCredentials: () => Promise<MockMateCredentials | null>;
  saveCredentials: (credentials: MockMateCredentials, remember: boolean) => Promise<CredentialStatus>;
  clearCredentials: () => Promise<void>;
  testCredentials: (credentials: MockMateCredentials) => Promise<ProviderTest[]>;
  startMockMate: (credentials: MockMateCredentials, remember: boolean) => Promise<StartResult>;
  stopMockMate: () => Promise<void>;
  onServiceEvent: (listener: (event: ServiceEvent) => void) => () => void;
};
