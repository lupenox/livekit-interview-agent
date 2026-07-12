import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type CreditStatus = 'ok' | 'low' | 'critical' | 'unavailable';

type ProviderCredit = {
  provider: 'ElevenLabs' | 'Deepgram' | 'Groq';
  label: string;
  status: CreditStatus;
  remaining: number | null;
  limit: number | null;
  unit: string;
  percentRemaining: number | null;
  detail?: string;
};

type ElevenLabsSubscription = {
  character_count?: number;
  character_limit?: number;
  next_character_count_reset_unix?: number | null;
};

type DeepgramProjectsResponse = {
  projects?: Array<{ project_id?: string; name?: string }>;
};

type DeepgramBalancesResponse = {
  balances?: Array<{ amount?: number | string; units?: string }>;
};

function statusFromPercent(percent: number): CreditStatus {
  if (percent <= 10) return 'critical';
  if (percent <= 25) return 'low';
  return 'ok';
}

function unavailable(
  provider: ProviderCredit['provider'],
  label: string,
  detail: string,
): ProviderCredit {
  return {
    provider,
    label,
    status: 'unavailable',
    remaining: null,
    limit: null,
    unit: '',
    percentRemaining: null,
    detail,
  };
}

async function getElevenLabsCredits(): Promise<ProviderCredit> {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  if (!apiKey) {
    return unavailable('ElevenLabs', 'Voice credits', 'ELEVENLABS_API_KEY is not configured.');
  }

  const response = await fetch('https://api.elevenlabs.io/v1/user/subscription', {
    headers: { 'xi-api-key': apiKey },
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`ElevenLabs returned ${response.status}`);
  }

  const data = (await response.json()) as ElevenLabsSubscription;
  const used = Number(data.character_count ?? 0);
  const limit = Number(data.character_limit ?? 0);

  if (!Number.isFinite(limit) || limit <= 0) {
    return unavailable('ElevenLabs', 'Voice credits', 'The subscription limit was not available.');
  }

  const remaining = Math.max(limit - used, 0);
  const percentRemaining = (remaining / limit) * 100;
  const resetDate = data.next_character_count_reset_unix
    ? new Date(data.next_character_count_reset_unix * 1000).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      })
    : null;

  return {
    provider: 'ElevenLabs',
    label: 'Voice credits',
    status: statusFromPercent(percentRemaining),
    remaining,
    limit,
    unit: 'characters',
    percentRemaining,
    detail: resetDate ? `Resets ${resetDate}` : undefined,
  };
}

async function getDeepgramCredits(): Promise<ProviderCredit> {
  const apiKey = process.env.DEEPGRAM_API_KEY;
  if (!apiKey) {
    return unavailable('Deepgram', 'Speech balance', 'DEEPGRAM_API_KEY is not configured.');
  }

  let projectId = process.env.DEEPGRAM_PROJECT_ID;
  let projectName: string | undefined;

  if (!projectId) {
    const projectsResponse = await fetch('https://api.deepgram.com/v1/projects', {
      headers: { Authorization: `Token ${apiKey}` },
      cache: 'no-store',
    });

    if (projectsResponse.status === 403) {
      return unavailable(
        'Deepgram',
        'Speech balance',
        'This API key is not permitted to list project billing data (HTTP 403). Transcription can still work normally.',
      );
    }

    if (!projectsResponse.ok) {
      throw new Error(`Deepgram projects returned ${projectsResponse.status}`);
    }

    const projects = (await projectsResponse.json()) as DeepgramProjectsResponse;
    const project = projects.projects?.[0];
    projectId = project?.project_id;
    projectName = project?.name;
  }

  if (!projectId) {
    return unavailable('Deepgram', 'Speech balance', 'No Deepgram project was available.');
  }

  const balanceResponse = await fetch(
    `https://api.deepgram.com/v1/projects/${encodeURIComponent(projectId)}/balances`,
    {
      headers: { Authorization: `Token ${apiKey}` },
      cache: 'no-store',
    },
  );

  if (balanceResponse.status === 403) {
    return unavailable(
      'Deepgram',
      'Speech balance',
      'This API key can use speech services but is not permitted to read project billing (HTTP 403). Use an account/key with billing access or check the Deepgram console.',
    );
  }

  if (!balanceResponse.ok) {
    throw new Error(`Deepgram balances returned ${balanceResponse.status}`);
  }

  const data = (await balanceResponse.json()) as DeepgramBalancesResponse;
  const balances = data.balances ?? [];
  const primaryUnit = balances.find((balance) => balance.units)?.units ?? 'credits';
  const remaining = balances
    .filter((balance) => (balance.units ?? primaryUnit) === primaryUnit)
    .reduce((sum, balance) => sum + Number(balance.amount ?? 0), 0);

  if (!Number.isFinite(remaining)) {
    return unavailable('Deepgram', 'Speech balance', 'The project balance was not available.');
  }

  const lowThreshold = Number(process.env.DEEPGRAM_LOW_BALANCE ?? 5);
  const criticalThreshold = Number(process.env.DEEPGRAM_CRITICAL_BALANCE ?? 1);
  const status: CreditStatus =
    remaining <= criticalThreshold ? 'critical' : remaining <= lowThreshold ? 'low' : 'ok';

  return {
    provider: 'Deepgram',
    label: 'Speech balance',
    status,
    remaining,
    limit: null,
    unit: primaryUnit,
    percentRemaining: null,
    detail: projectName,
  };
}

function parseHeaderNumber(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

async function getGroqLimits(): Promise<ProviderCredit> {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) {
    return unavailable('Groq', 'Rate-limit headroom', 'GROQ_API_KEY is not configured.');
  }

  const response = await fetch('https://api.groq.com/openai/v1/models', {
    headers: { Authorization: `Bearer ${apiKey}` },
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(`Groq returned ${response.status}`);
  }

  const requestsRemaining = parseHeaderNumber(response.headers.get('x-ratelimit-remaining-requests'));
  const requestsLimit = parseHeaderNumber(response.headers.get('x-ratelimit-limit-requests'));
  const tokensRemaining = parseHeaderNumber(response.headers.get('x-ratelimit-remaining-tokens'));
  const tokensLimit = parseHeaderNumber(response.headers.get('x-ratelimit-limit-tokens'));

  const percentages = [
    requestsRemaining !== null && requestsLimit ? (requestsRemaining / requestsLimit) * 100 : null,
    tokensRemaining !== null && tokensLimit ? (tokensRemaining / tokensLimit) * 100 : null,
  ].filter((value): value is number => value !== null && Number.isFinite(value));

  if (percentages.length === 0) {
    return unavailable(
      'Groq',
      'Rate-limit headroom',
      'Groq authenticated successfully, but the models endpoint did not return rate-limit headers. Exact limits remain available in the Groq console.',
    );
  }

  const percentRemaining = Math.min(...percentages);
  const requestCopy =
    requestsRemaining !== null && requestsLimit !== null
      ? `${Math.round(requestsRemaining).toLocaleString()} daily requests left`
      : null;
  const tokenCopy =
    tokensRemaining !== null && tokensLimit !== null
      ? `${Math.round(tokensRemaining).toLocaleString()} tokens/min left`
      : null;

  return {
    provider: 'Groq',
    label: 'Rate-limit headroom',
    status: statusFromPercent(percentRemaining),
    remaining: requestsRemaining ?? tokensRemaining,
    limit: requestsLimit ?? tokensLimit,
    unit: requestsRemaining !== null ? 'daily requests' : 'tokens/min',
    percentRemaining,
    detail: [requestCopy, tokenCopy].filter(Boolean).join(' · '),
  };
}

async function safeProvider(
  provider: ProviderCredit['provider'],
  label: string,
  loader: () => Promise<ProviderCredit>,
): Promise<ProviderCredit> {
  try {
    return await loader();
  } catch (error) {
    console.error(`[credits] ${provider}`, error);
    return unavailable(provider, label, 'Usage data is temporarily unavailable.');
  }
}

export async function GET() {
  const providers = await Promise.all([
    safeProvider('ElevenLabs', 'Voice credits', getElevenLabsCredits),
    safeProvider('Deepgram', 'Speech balance', getDeepgramCredits),
    safeProvider('Groq', 'Rate-limit headroom', getGroqLimits),
  ]);

  return NextResponse.json(
    { providers, checkedAt: new Date().toISOString() },
    { headers: { 'Cache-Control': 'no-store, max-age=0' } },
  );
}
