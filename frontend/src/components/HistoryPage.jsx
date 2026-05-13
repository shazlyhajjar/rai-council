import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { api } from '../api';
import { MODES, findMode } from '../modes';
import { identityFor } from '../modelIdentity';
import CopyButton from './CopyButton';
import './HistoryPage.css';

const DECISION_FILTERS = [
  { key: '', label: 'All decisions' },
  { key: 'undecided', label: 'Undecided' },
  { key: 'accept', label: 'Accepted' },
  { key: 'override', label: 'Overridden' },
];

function fmtTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function decisionBadge(decision) {
  if (decision === 'accept') return <span className="history-pill accepted">Accepted</span>;
  if (decision === 'override') return <span className="history-pill overridden">Overridden</span>;
  return <span className="history-pill undecided">Undecided</span>;
}

export default function HistoryPage() {
  const [verdicts, setVerdicts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modeFilter, setModeFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [activeId, setActiveId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.listVerdicts({
        mode: modeFilter || undefined,
        decision: decisionFilter || undefined,
      });
      setVerdicts(result.verdicts || []);
    } catch (err) {
      setError(err.message || 'Failed to load verdicts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeFilter, decisionFilter]);

  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setDetailLoading(true);
      try {
        const v = await api.getVerdict(activeId);
        if (!cancelled) setDetail(v);
      } catch (err) {
        if (!cancelled) setDetail({ error: err.message });
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const handleDecide = async (decision, reasoning) => {
    if (!activeId) return;
    try {
      const updated = await api.decideVerdict(activeId, decision, reasoning);
      setDetail(updated);
      // refresh the row in the list view
      setVerdicts((prev) =>
        prev.map((v) =>
          v.id === activeId
            ? {
                ...v,
                decision: updated.decision,
                override_reasoning: updated.override_reasoning,
                decided_at: updated.decided_at,
              }
            : v,
        ),
      );
    } catch (err) {
      alert(`Save failed: ${err.message}`);
    }
  };

  const total = verdicts.length;
  const counts = useMemo(() => {
    const acc = { accept: 0, override: 0, undecided: 0 };
    verdicts.forEach((v) => {
      if (v.decision === 'accept') acc.accept += 1;
      else if (v.decision === 'override') acc.override += 1;
      else acc.undecided += 1;
    });
    return acc;
  }, [verdicts]);

  return (
    <div className="history-page">
      <div className="history-list-pane">
        <header className="history-header">
          <h2>Verdict log</h2>
          <p>
            {total.toLocaleString()} verdict{total === 1 ? '' : 's'} ·{' '}
            <span className="history-count-chip accepted">{counts.accept} accepted</span>{' '}
            <span className="history-count-chip overridden">{counts.override} overridden</span>{' '}
            <span className="history-count-chip undecided">{counts.undecided} open</span>
          </p>
        </header>

        <div className="history-filters">
          <label>
            <span className="history-filter-label">Mode</span>
            <select value={modeFilter} onChange={(e) => setModeFilter(e.target.value)}>
              <option value="">All modes</option>
              {MODES.filter((m) => m.key).map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
              <option value="">Free chat</option>
            </select>
          </label>
          <label>
            <span className="history-filter-label">Decision</span>
            <select
              value={decisionFilter}
              onChange={(e) => setDecisionFilter(e.target.value)}
            >
              {DECISION_FILTERS.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="history-refresh" onClick={refresh}>
            Refresh
          </button>
        </div>

        {error && <div className="history-error">{error}</div>}
        {loading ? (
          <div className="history-empty">Loading…</div>
        ) : verdicts.length === 0 ? (
          <div className="history-empty">No verdicts match the current filters.</div>
        ) : (
          <ul className="history-rows">
            {verdicts.map((v) => {
              const isActive = activeId === v.id;
              const modeLabel = v.mode ? findMode(v.mode).label : 'Free Chat';
              return (
                <li key={v.id}>
                  <button
                    type="button"
                    className={`history-row ${isActive ? 'active' : ''}`}
                    onClick={() => setActiveId(v.id)}
                  >
                    <div className="history-row-top">
                      <span className="history-row-mode">{modeLabel}</span>
                      {decisionBadge(v.decision)}
                    </div>
                    <div className="history-row-question">{v.question || '(no question)'}</div>
                    <div className="history-row-meta">{fmtTime(v.created_at)}</div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="history-detail-pane">
        {!activeId && <div className="history-empty">Select a verdict to inspect.</div>}
        {activeId && detailLoading && <div className="history-empty">Loading verdict…</div>}
        {activeId && !detailLoading && detail && !detail.error && (
          <HistoryDetail verdict={detail} onDecide={handleDecide} />
        )}
        {activeId && detail?.error && <div className="history-error">{detail.error}</div>}
      </div>
    </div>
  );
}

function HistoryDetail({ verdict, onDecide }) {
  const [overrideText, setOverrideText] = useState(verdict.override_reasoning || '');
  const [showOverride, setShowOverride] = useState(false);

  useEffect(() => {
    setOverrideText(verdict.override_reasoning || '');
    setShowOverride(false);
  }, [verdict.id, verdict.override_reasoning]);

  const modeLabel = verdict.mode ? findMode(verdict.mode).label : 'Free Chat';

  return (
    <div className="history-detail">
      <header className="history-detail-header">
        <div>
          <div className="history-detail-eyebrow">
            {modeLabel} · {fmtTime(verdict.created_at)}
          </div>
          <h3>{verdict.question_full || verdict.question}</h3>
        </div>
        {decisionBadge(verdict.decision)}
      </header>

      <section className="history-detail-section">
        <h4>Council positions</h4>
        {(verdict.model_positions || []).map((pos, i) => {
          const id = identityFor(pos.model);
          const tag = pos.role || (pos.stance ? pos.stance.toUpperCase() : null);
          return (
            <div key={i} className="history-position">
              <div className="history-position-header">
                <span className="history-position-name" style={{ color: id.color }}>
                  {id.name}
                </span>
                <span className="history-position-subtitle">{id.subtitle}</span>
                {tag && <span className="history-position-tag">{tag}</span>}
              </div>
              <div className="history-position-body markdown-content">
                <ReactMarkdown>{(pos.response || '').slice(0, 1200) + ((pos.response || '').length > 1200 ? '…' : '')}</ReactMarkdown>
              </div>
            </div>
          );
        })}
      </section>

      <section className="history-detail-section">
        <div className="history-detail-section-header">
          <h4>Chairman verdict</h4>
          <CopyButton getText={() => verdict.chairman_verdict || ''} title="Copy verdict" />
        </div>
        <div className="history-position-header">
          <span className="history-position-name" style={{ color: '#15803d' }}>
            Council Chairman
          </span>
          <span className="history-position-subtitle">Synthesis &amp; Verdict</span>
        </div>
        <div className="history-chairman markdown-content">
          <ReactMarkdown>{verdict.chairman_verdict || ''}</ReactMarkdown>
        </div>
      </section>

      <section className="history-detail-section">
        <h4>Your decision</h4>
        {verdict.decision === 'accept' && (
          <div className="history-decision accepted">
            Accepted on {fmtTime(verdict.decided_at)}
          </div>
        )}
        {verdict.decision === 'override' && (
          <div className="history-decision overridden">
            <div>Overridden on {fmtTime(verdict.decided_at)}</div>
            {verdict.override_reasoning && (
              <div className="history-decision-reasoning">
                <span className="label">Reasoning</span>
                <p>{verdict.override_reasoning}</p>
              </div>
            )}
          </div>
        )}
        {!verdict.decision && (
          <div className="history-decision undecided">No decision recorded yet.</div>
        )}

        {!showOverride ? (
          <div className="history-decision-actions">
            <button
              type="button"
              className="chairman-decision-button accept"
              onClick={() => onDecide('accept')}
            >
              {verdict.decision === 'accept' ? 'Re-confirm accept' : 'Accept'}
            </button>
            <button
              type="button"
              className="chairman-decision-button override"
              onClick={() => setShowOverride(true)}
            >
              {verdict.decision === 'override' ? 'Update override' : 'Override'}
            </button>
          </div>
        ) : (
          <div className="history-override-form">
            <textarea
              className="chairman-decision-textarea"
              value={overrideText}
              onChange={(e) => setOverrideText(e.target.value)}
              placeholder="Why are you overriding this verdict?"
              rows={4}
            />
            <div className="history-decision-actions">
              <button
                type="button"
                className="chairman-decision-button secondary"
                onClick={() => setShowOverride(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="chairman-decision-button override"
                onClick={() => {
                  onDecide('override', overrideText);
                  setShowOverride(false);
                }}
              >
                Save override
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
