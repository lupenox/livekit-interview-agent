export type CreditStatus = 'ok' | 'low' | 'critical' | 'unavailable';

export type ProviderCredit = {
  provider: 'ElevenLabs' | 'Deepgram' | 'Groq';
  label: string;
  status: CreditStatus;
  remaining: number | null;
  limit: number | null;
  unit: string;
  percentRemaining: number | null;
  detail?: string;
};

export type CreditsResponse = {
  providers: ProviderCredit[];
  checkedAt: string;
};

export type ConnectionDetails = {
  serverUrl: string;
  participantToken: string;
  roomName: string;
  participantName: string;
};
