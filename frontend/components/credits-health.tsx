'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, RefreshCw, WalletCards } from 'lucide-react';

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

type CreditsResponse = {
  providers: ProviderCredit[];
  checkedAt: string;
};

const numberFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });

function formatPrimaryValue(provider: ProviderCredit): string {
  if (provider.remaining === null) return 'Unavailable';

  if (provider.unit.toLowerCase() === 'usd') {
    return `$${provider.remaining.toFixed(2)} remaining`;
  }

  if (provider.limit !== null) {
    return `${numberFormatter.format(provider.remaining)} of ${numberFormatter.format(provider.limit)} ${provider.unit} left`;
  }

  return `${numberFormatter.format(provider.remaining)} ${provider.unit} remaining`;
}

function overallStatus(providers: ProviderCredit[]): CreditStatus {
  if (providers.some((provider) => provider.status === 'critical')) return 'critical';
  if (providers.some((provider) => provider.status === 'low')) return 'low';
  if (providers.some((provider) => provider.status === 'ok')) return 'ok';
  return 'unavailable';
}

export function CreditsHealth() {
  const [data, setData] = useState<CreditsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCredits = useCallback(async () => {
    try {
      setError(null);
      const response = await fetch('/api/credits', { cache: 'no-store' });
      if (!response.ok) throw new Error(`Credits endpoint returned ${response.status}`);
      setData((await response.json()) as CreditsResponse);
    } catch (loadError) {
      console.error(loadError);
      setError('Could not refresh API usage.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCredits();
    const timer = window.setInterval(() => void loadCredits(), 60_000);
    return () => window.clearInterval(timer);
  }, [loadCredits]);

  const status = useMemo(() => overallStatus(data?.providers ?? []), [data]);
  const summary = loading
    ? 'Checking API budget…'
    : status === 'critical'
      ? 'API credits critical'
      : status === 'low'
        ? 'API credits running low'
        : status === 'ok'
          ? 'API budget healthy'
          : 'API usage unavailable';

  return (
    <details className={`credits-menu credits-${status}`}>
      <summary>
        <span className="credit-status-dot" aria-hidden="true" />
        <WalletCards size={17} />
        <span>{summary}</span>
      </summary>

      <div className="credits-popover">
        <div className="credits-popover-header">
          <div>
            <strong>API budget</strong>
            <span>Refreshes every minute</span>
          </div>
          <button type="button" onClick={() => void loadCredits()} aria-label="Refresh API usage">
            <RefreshCw size={16} />
          </button>
        </div>

        {error ? <div className="credits-error"><AlertTriangle size={15} />{error}</div> : null}

        <div className="credit-provider-list">
          {(data?.providers ?? []).map((provider) => {
            const percent =
              provider.percentRemaining === null
                ? null
                : Math.max(0, Math.min(100, provider.percentRemaining));

            return (
              <div className={`credit-provider credit-provider-${provider.status}`} key={provider.provider}>
                <div className="credit-provider-heading">
                  <div>
                    <strong>{provider.provider}</strong>
                    <span>{provider.label}</span>
                  </div>
                  <span className="credit-provider-state">{provider.status}</span>
                </div>
                <div className="credit-primary-value">{formatPrimaryValue(provider)}</div>
                {percent !== null ? (
                  <div className="credit-meter" aria-label={`${Math.round(percent)} percent remaining`}>
                    <span style={{ width: `${percent}%` }} />
                  </div>
                ) : null}
                {provider.detail ? <div className="credit-detail">{provider.detail}</div> : null}
              </div>
            );
          })}
        </div>

        {data?.checkedAt ? (
          <div className="credits-checked-at">
            Updated {new Date(data.checkedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
          </div>
        ) : null}
      </div>
    </details>
  );
}
