import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import './ContextEditor.css';

function formatUpdatedAt(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

/**
 * Modal editor for the RAI Council Brief. Opens populated from the server,
 * saves on click, closes on success.
 */
export default function ContextEditor({ onClose, onSaved }) {
  const [status, setStatus] = useState(null);
  const [draft, setDraft] = useState('');
  const [loadError, setLoadError] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [saving, setSaving] = useState(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.getContext();
        if (cancelled) return;
        setStatus(s);
        setDraft(s.content || '');
        setLoadError(null);
      } catch (err) {
        if (!cancelled) setLoadError(err.message || 'Failed to load');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // Close on Escape
    const onKey = (e) => {
      if (e.key === 'Escape' && !saving) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, saving]);

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const next = await api.setContext(draft);
      setStatus(next);
      onSaved?.(next);
    } catch (err) {
      setSaveError(err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget && !saving) onClose();
  };

  const wordCount = draft.trim() ? draft.trim().split(/\s+/).length : 0;
  const charCount = draft.length;

  return (
    <div className="context-editor-backdrop" onClick={handleBackdropClick}>
      <div className="context-editor-panel" role="dialog" aria-modal="true" aria-labelledby="context-editor-title">
        <header className="context-editor-header">
          <div>
            <h2 id="context-editor-title">RAI Council Brief</h2>
            <p className="context-editor-subtitle">
              Auto-loaded as system context for every council member and the Chairman.
            </p>
          </div>
          <button
            type="button"
            className="context-editor-close"
            onClick={onClose}
            disabled={saving}
            aria-label="Close editor"
          >
            ×
          </button>
        </header>

        {loadError ? (
          <div className="context-editor-error">Failed to load: {loadError}</div>
        ) : (
          <>
            <div className="context-editor-meta">
              <div>
                <span className="context-editor-meta-label">File</span>
                <code>{status?.path || '…'}</code>
              </div>
              <div>
                <span className="context-editor-meta-label">Last updated</span>
                <span>{formatUpdatedAt(status?.updated_at) || '—'}</span>
              </div>
              <div>
                <span className="context-editor-meta-label">Length</span>
                <span>{wordCount.toLocaleString()} words · {charCount.toLocaleString()} chars</span>
              </div>
            </div>

            <textarea
              ref={textareaRef}
              className="context-editor-textarea"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
              disabled={saving}
              placeholder="Paste the council brief here. Plain text or markdown."
            />

            {saveError && (
              <div className="context-editor-error">Save failed: {saveError}</div>
            )}

            <footer className="context-editor-footer">
              <button
                type="button"
                className="context-editor-button secondary"
                onClick={onClose}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                type="button"
                className="context-editor-button primary"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? 'Saving…' : 'Save brief'}
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
