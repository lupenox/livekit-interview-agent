import { RoomServiceClient } from 'livekit-server-sdk';
import type { MockMateCredentials, ProviderTest } from './types';

const REQUEST_TIMEOUT_MS = 10_000;

async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
  return fetch(url, { ...init, signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
}

function liveKitHttpUrl(url: string): string {
  const parsed = new URL(url.trim());
  if (parsed.protocol === 'wss:') parsed.protocol = 'https:';
  if (parsed.protocol === 'ws:') parsed.protocol = 'http:';
  return parsed.toString().replace(/\/$/, '');
}

async function testLiveKit(credentials: MockMateCredentials): Promise<ProviderTest> {
  try {
    const client = new RoomServiceClient(
      liveKitHttpUrl(credentials.livekitUrl),
      credentials.livekitApiKey,
      credentials.livekitApiSecret,
    );
    await client.listRooms();
    return { provider: 'LiveKit', ok: true, message: 'Project credentials accepted.' };
  } catch {
    return { provider: 'LiveKit', ok: false, message: 'Could not authenticate with this LiveKit project.' };
  }
}

async function testBearerProvider(
  provider: 'Groq' | 'Deepgram' | 'ElevenLabs',
  url: string,
  headers: Record<string, string>,
): Promise<ProviderTest> {
  try {
    const response = await fetchWithTimeout(url, { headers, cache: 'no-store' });
    if (!response.ok) {
      return { provider, ok: false, message: `Provider returned HTTP ${response.status}.` };
    }
    return { provider, ok: true, message: 'Credential accepted.' };
  } catch {
    return { provider, ok: false, message: 'Provider could not be reached.' };
  }
}

export async function testCredentials(credentials: MockMateCredentials): Promise<ProviderTest[]> {
  return Promise.all([
    testLiveKit(credentials),
    testBearerProvider('Groq', 'https://api.groq.com/openai/v1/models', {
      Authorization: `Bearer ${credentials.groqApiKey}`,
    }),
    testBearerProvider('Deepgram', 'https://api.deepgram.com/v1/projects', {
      Authorization: `Token ${credentials.deepgramApiKey}`,
    }),
    testBearerProvider('ElevenLabs', 'https://api.elevenlabs.io/v1/user/subscription', {
      'xi-api-key': credentials.elevenlabsApiKey,
    }),
  ]);
}
