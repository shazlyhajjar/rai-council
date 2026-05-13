import { useEffect, useState } from 'react';
import { api } from '../api';
import ContextEditor from './ContextEditor';
import './ContextStatus.css';

function formatUpdatedAt(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

/**
 * Top-bar indicator showing whether the RAI Council Brief is loaded.
 * Clicking it opens the editor modal.
 */
export default function ContextStatus() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [editorOpen, setEditorOpen] = useState(false);

  const refresh = async () => {
    try {
      const s = await api.getContext();
      setStatus(s);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load');
      setStatus(null);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  let label;
  let className = 'context-status';

  if (error) {
    label = 'RAI Context: error';
    className += ' is-error';
  } else if (!status) {
    label = 'RAI Context: …';
    className += ' is-loading';
  } else if (status.loaded) {
    label = `RAI Context: loaded · ${status.words.toLocaleString()} words`;
    className += ' is-loaded';
  } else {
    label = 'RAI Context: not loaded';
    className += ' is-missing';
  }

  const updatedAt = status?.updated_at ? formatUpdatedAt(status.updated_at) : null;
  const tooltip = status?.loaded
    ? `Loaded from ${status.path}${updatedAt ? `\nLast updated ${updatedAt}` : ''}\nClick to edit`
    : 'Click to add or edit the council brief';

  return (
    <>
      <button
        type="button"
        className={className}
        onClick={() => setEditorOpen(true)}
        title={tooltip}
      >
        <span className="context-status-dot" aria-hidden="true" />
        <span className="context-status-label">{label}</span>
      </button>

      {editorOpen && (
        <ContextEditor
          onClose={() => setEditorOpen(false)}
          onSaved={(next) => {
            setStatus(next);
            setEditorOpen(false);
          }}
        />
      )}
    </>
  );
}
