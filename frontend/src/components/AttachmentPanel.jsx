import { useState } from 'react';
import './AttachmentPanel.css';

const PREVIEW_CHARS = 220;

function summarize(text) {
  const trimmed = text.trim();
  const chars = trimmed.length;
  const lines = trimmed.split(/\r?\n/).length;
  const words = trimmed ? trimmed.split(/\s+/).length : 0;
  return { chars, lines, words };
}

export default function AttachmentPanel({ value, onChange, disabled }) {
  const [expanded, setExpanded] = useState(false);

  const hasContent = value && value.trim().length > 0;
  const { chars, lines, words } = hasContent ? summarize(value) : { chars: 0, lines: 0, words: 0 };

  const showEditor = !hasContent || expanded;

  return (
    <div className={`attachment-panel ${hasContent ? 'has-content' : ''}`}>
      <div className="attachment-header">
        <span className="attachment-label">Attachment</span>
        <span className="attachment-hint">
          Paste a spec, code snippet, or document. Included as context for every council member.
        </span>
        {hasContent && (
          <div className="attachment-actions">
            <button
              type="button"
              className="attachment-toggle"
              onClick={() => setExpanded((v) => !v)}
              disabled={disabled}
            >
              {expanded ? 'Collapse' : 'Edit'}
            </button>
            <button
              type="button"
              className="attachment-clear"
              onClick={() => {
                onChange('');
                setExpanded(false);
              }}
              disabled={disabled}
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {showEditor ? (
        <textarea
          className="attachment-textarea"
          placeholder="Paste anything you want the council to read alongside your question…"
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          rows={hasContent ? 8 : 4}
        />
      ) : (
        <button
          type="button"
          className="attachment-preview"
          onClick={() => setExpanded(true)}
          disabled={disabled}
          title="Click to edit"
        >
          <div className="attachment-stats">
            {words.toLocaleString()} words · {lines.toLocaleString()} lines · {chars.toLocaleString()} chars
          </div>
          <div className="attachment-snippet">
            {value.trim().slice(0, PREVIEW_CHARS)}
            {chars > PREVIEW_CHARS ? '…' : ''}
          </div>
        </button>
      )}
    </div>
  );
}
