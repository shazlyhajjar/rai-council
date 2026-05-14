import { useEffect, useState, useCallback } from 'react';
import { api } from '../api';
import './BalanceIndicator.css';

const REFRESH_MS = 60_000;

function fmt(amount) {
  if (amount == null || Number.isNaN(amount)) return '—';
  if (amount >= 100) return `$${amount.toFixed(0)}`;
  return `$${amount.toFixed(2)}`;
}

/**
 * Pick a health color based on the fraction of the budget consumed.
 * green = comfortable, amber = warming, red = nearly out, grey = unknown.
 */
function dotForFraction(usedFraction) {
  if (usedFraction == null || Number.isNaN(usedFraction)) return 'unknown';
  if (usedFraction >= 0.9) return 'red';
  if (usedFraction >= 0.75) return 'amber';
  return 'green';
}

function Pill({ label, primary, secondary, tooltip, dot, error, onRefresh }) {
  const className = `balance-pill ${error ? 'is-error' : ''}`;
  return (
    <button
      type="button"
      className={className}
      title={tooltip}
      onClick={onRefresh}
    >
      <span className={`balance-dot dot-${dot}`} />
      <span className="balance-label">{label}</span>
      <span className="balance-primary">{error ? 'unavailable' : primary}</span>
      {!error && secondary && <span className="balance-secondary">{secondary}</span>}
    </button>
  );
}

function renderOpenRouter(data, onRefresh) {
  if (!data) {
    return <Pill label="OpenRouter" primary="…" dot="unknown" tooltip="Loading…" onRefresh={onRefresh} />;
  }
  if (data.error) {
    return (
      <Pill
        label="OpenRouter"
        error
        dot="unknown"
        tooltip={`OpenRouter: ${data.error}`}
        onRefresh={onRefresh}
      />
    );
  }
  const used = data.total_credits > 0 ? data.total_usage / data.total_credits : null;
  const dot = dotForFraction(used);
  const tooltip = [
    `OpenRouter balance`,
    `Total credits: ${fmt(data.total_credits)}`,
    `Used: ${fmt(data.total_usage)}`,
    `Remaining: ${fmt(data.remaining)}`,
    `Fetched: ${data.fetched_at}`,
    `(click to refresh)`,
  ].join('\n');
  return (
    <Pill
      label="OpenRouter"
      primary={fmt(data.remaining)}
      secondary={`/ ${fmt(data.total_credits)}`}
      dot={dot}
      tooltip={tooltip}
      onRefresh={onRefresh}
    />
  );
}

function renderOpenAI(data, onRefresh) {
  if (!data) {
    return <Pill label="OpenAI" primary="…" dot="unknown" tooltip="Loading…" onRefresh={onRefresh} />;
  }
  if (data.error) {
    return (
      <Pill
        label="OpenAI"
        error
        dot="unknown"
        tooltip={`OpenAI: ${data.error}${data.error_detail ? `\n${data.error_detail}` : ''}`}
        onRefresh={onRefresh}
      />
    );
  }
  const cap = data.monthly_cap;
  const spent = data.spent_this_month;
  const used = cap != null && cap > 0 ? spent / cap : null;
  const dot = used != null ? dotForFraction(used) : 'unknown';

  const tooltipLines = [
    `OpenAI month-to-date spend`,
    `Spent: ${fmt(spent)}`,
  ];
  if (cap != null) {
    tooltipLines.push(`Cap: ${fmt(cap)}`);
    tooltipLines.push(`Remaining: ${fmt(data.remaining)}`);
  } else {
    tooltipLines.push(`Cap: (not configured — set OPENAI_MONTHLY_CAP in .env to enable)`);
  }
  tooltipLines.push(`Fetched: ${data.fetched_at}`);
  tooltipLines.push(`(click to refresh)`);

  return (
    <Pill
      label="OpenAI"
      primary={cap != null ? fmt(data.remaining) : fmt(spent)}
      secondary={cap != null ? `/ ${fmt(cap)}` : 'spent'}
      dot={dot}
      tooltip={tooltipLines.join('\n')}
      onRefresh={onRefresh}
    />
  );
}

export default function BalanceIndicator() {
  const [openrouter, setOpenrouter] = useState(null);
  const [openai, setOpenai] = useState(null);

  const refreshOpenRouter = useCallback(async () => {
    try {
      const data = await api.getOpenRouterBalance();
      setOpenrouter(data);
    } catch (e) {
      setOpenrouter({ error: e.message || 'fetch failed' });
    }
  }, []);

  const refreshOpenAI = useCallback(async () => {
    try {
      const data = await api.getOpenAIBalance();
      setOpenai(data);
    } catch (e) {
      setOpenai({ error: e.message || 'fetch failed' });
    }
  }, []);

  useEffect(() => {
    refreshOpenRouter();
    refreshOpenAI();
    const id = setInterval(() => {
      refreshOpenRouter();
      refreshOpenAI();
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, [refreshOpenRouter, refreshOpenAI]);

  return (
    <div className="balance-indicator">
      {renderOpenRouter(openrouter, refreshOpenRouter)}
      {renderOpenAI(openai, refreshOpenAI)}
    </div>
  );
}
