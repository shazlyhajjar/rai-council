import { useEffect, useState } from 'react';
import { api } from '../api';
import './ChairmanDecision.css';

/**
 * Accept / Override controls for a Chairman synthesis.
 *
 * Props:
 *   verdictId      — required to record a decision (omit while still streaming)
 *   verdict        — optional current verdict state ({decision, override_reasoning, decided_at})
 *   onDecided      — callback called with the updated verdict after a successful save
 */
export default function ChairmanDecision({ verdictId, verdict, onDecided }) {
  const [decision, setDecision] = useState(verdict?.decision || null);
  const [reasoning, setReasoning] = useState(verdict?.override_reasoning || '');
  const [showOverrideInput, setShowOverrideInput] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Re-sync if the server-side verdict state changes (e.g. on conversation reload).
  useEffect(() => {
    setDecision(verdict?.decision || null);
    setReasoning(verdict?.override_reasoning || '');
    setShowOverrideInput(false);
  }, [verdict?.decision, verdict?.override_reasoning]);

  if (!verdictId) {
    return (
      <div className="chairman-decision pending">
        Saving verdict to the log…
      </div>
    );
  }

  const handleAccept = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.decideVerdict(verdictId, 'accept');
      setDecision('accept');
      onDecided?.(updated);
    } catch (err) {
      setError(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleSubmitOverride = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.decideVerdict(verdictId, 'override', reasoning);
      setDecision('override');
      setShowOverrideInput(false);
      onDecided?.(updated);
    } catch (err) {
      setError(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleReopen = () => {
    setShowOverrideInput(false);
    setDecision(null);
    setReasoning(verdict?.override_reasoning || '');
  };

  if (decision === 'accept') {
    return (
      <div className="chairman-decision decided accepted">
        <span className="chairman-decision-badge">Accepted</span>
        <span className="chairman-decision-detail">Verdict adopted as-is.</span>
        <button type="button" className="chairman-decision-link" onClick={handleReopen}>
          Reopen
        </button>
      </div>
    );
  }

  if (decision === 'override') {
    return (
      <div className="chairman-decision decided overridden">
        <span className="chairman-decision-badge">Overridden</span>
        {verdict?.override_reasoning && (
          <div className="chairman-decision-reasoning">
            <span className="label">Your reasoning</span>
            <p>{verdict.override_reasoning}</p>
          </div>
        )}
        <button type="button" className="chairman-decision-link" onClick={handleReopen}>
          Reopen
        </button>
      </div>
    );
  }

  return (
    <div className="chairman-decision">
      {!showOverrideInput ? (
        <>
          <div className="chairman-decision-prompt">Adopt this verdict?</div>
          <div className="chairman-decision-actions">
            <button
              type="button"
              className="chairman-decision-button accept"
              onClick={handleAccept}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Accept'}
            </button>
            <button
              type="button"
              className="chairman-decision-button override"
              onClick={() => setShowOverrideInput(true)}
              disabled={saving}
            >
              Override
            </button>
          </div>
          {error && <div className="chairman-decision-error">{error}</div>}
        </>
      ) : (
        <>
          <label className="chairman-decision-prompt" htmlFor={`override-${verdictId}`}>
            Why are you overriding this verdict?
          </label>
          <textarea
            id={`override-${verdictId}`}
            className="chairman-decision-textarea"
            value={reasoning}
            onChange={(e) => setReasoning(e.target.value)}
            placeholder="Your reasoning (saved with the verdict)…"
            rows={3}
            disabled={saving}
          />
          <div className="chairman-decision-actions">
            <button
              type="button"
              className="chairman-decision-button secondary"
              onClick={() => setShowOverrideInput(false)}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="button"
              className="chairman-decision-button override"
              onClick={handleSubmitOverride}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Save override'}
            </button>
          </div>
          {error && <div className="chairman-decision-error">{error}</div>}
        </>
      )}
    </div>
  );
}
