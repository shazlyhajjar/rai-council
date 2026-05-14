import { useRef, useState } from 'react';
import './AttachmentPanel.css';

const PREVIEW_CHARS = 220;

// Hard ceiling per file. Above this we refuse — the prompt would balloon
// past most lane context limits and tank latency. Reasonable text files
// (specs, code, configs, docs) easily fit under 1 MB.
const MAX_BYTES_PER_FILE = 1_000_000;

// File extensions we trust to be text. Browsers don't always set a MIME type,
// so extension is the most reliable signal. Anything else still passes through
// the binary-content sniff below.
const TEXT_EXTENSIONS = [
  // prose / docs
  'txt', 'md', 'markdown', 'rst', 'log',
  // code
  'py', 'js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs',
  'go', 'rs', 'rb', 'php', 'java', 'kt', 'swift',
  'c', 'cc', 'cpp', 'h', 'hpp', 'cs',
  'sh', 'bash', 'zsh', 'fish',
  'sql', 'graphql', 'proto',
  'html', 'htm', 'css', 'scss', 'sass', 'less',
  'vue', 'svelte',
  // config / data
  'json', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf',
  'xml', 'csv', 'tsv',
];

function summarize(text) {
  const trimmed = text.trim();
  const chars = trimmed.length;
  const lines = trimmed.split(/\r?\n/).length;
  const words = trimmed ? trimmed.split(/\s+/).length : 0;
  return { chars, lines, words };
}

function extOf(name) {
  const ix = name.lastIndexOf('.');
  return ix >= 0 ? name.slice(ix + 1).toLowerCase() : '';
}

/**
 * Heuristic: does `text` look like binary content?
 * Counts control characters in the first 4 KB (excluding tab/newline/CR).
 * If >5% of the sample is control bytes, treat as binary.
 */
function looksBinary(text) {
  const sample = text.slice(0, 4096);
  if (sample.length === 0) return false;
  let control = 0;
  for (let i = 0; i < sample.length; i += 1) {
    const code = sample.charCodeAt(i);
    if (code === 9 || code === 10 || code === 13) continue;
    if (code < 32 || code === 0xfffd) control += 1;
  }
  return control / sample.length > 0.05;
}

function readAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error || new Error('read failed'));
    reader.readAsText(file);
  });
}

/**
 * Wrap a file's text in a markdown block the council can scan. Filename
 * heading + fenced code block tagged with the language hint from the
 * extension (so syntax-aware models render it cleanly).
 */
function wrapFile(name, text) {
  const ext = extOf(name);
  const fence = TEXT_EXTENSIONS.includes(ext) ? ext : '';
  // Use ```` if the file contains ``` to avoid accidentally closing the fence.
  const tick = text.includes('```') ? '````' : '```';
  return `### ${name}\n${tick}${fence}\n${text}\n${tick}`;
}

export default function AttachmentPanel({ value, onChange, disabled }) {
  const [expanded, setExpanded] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [errors, setErrors] = useState([]); // [{name, reason}]
  const fileInputRef = useRef(null);

  const hasContent = value && value.trim().length > 0;
  const { chars, lines, words } = hasContent ? summarize(value) : { chars: 0, lines: 0, words: 0 };
  const showEditor = !hasContent || expanded;

  async function ingestFiles(fileList) {
    if (!fileList || fileList.length === 0) return;
    const nextErrors = [];
    const blocks = [];

    for (const file of Array.from(fileList)) {
      if (file.size > MAX_BYTES_PER_FILE) {
        nextErrors.push({
          name: file.name,
          reason: `too large (${(file.size / 1024).toFixed(0)} KB > 1 MB cap)`,
        });
        continue;
      }
      try {
        const text = await readAsText(file);
        if (looksBinary(text)) {
          nextErrors.push({
            name: file.name,
            reason: 'looks binary (not a text file)',
          });
          continue;
        }
        blocks.push(wrapFile(file.name, text));
      } catch (e) {
        nextErrors.push({
          name: file.name,
          reason: e.message || 'read failed',
        });
      }
    }

    setErrors(nextErrors);
    if (blocks.length === 0) return;

    const combined = blocks.join('\n\n');
    const next = hasContent ? `${value.trimEnd()}\n\n${combined}` : combined;
    onChange(next);
    setExpanded(true);
  }

  function onFileInputChange(e) {
    ingestFiles(e.target.files);
    // Reset so picking the same file again still fires onChange.
    e.target.value = '';
  }

  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    ingestFiles(e.dataTransfer?.files);
  }

  function onDragOver(e) {
    if (disabled) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    setDragging(true);
  }

  function onDragLeave(e) {
    // Only un-highlight when leaving the panel itself, not a child node.
    if (e.currentTarget.contains(e.relatedTarget)) return;
    setDragging(false);
  }

  return (
    <div
      className={`attachment-panel ${hasContent ? 'has-content' : ''} ${dragging ? 'is-dragging' : ''}`}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
    >
      <div className="attachment-header">
        <span className="attachment-label">Attachment</span>
        <span className="attachment-hint">
          Paste, drop, or pick a file. Included as context for every council member.
        </span>
        <div className="attachment-actions">
          <button
            type="button"
            className="attachment-attach"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            title="Attach one or more text files (code, specs, configs…) — max 1 MB each"
          >
            Attach files
          </button>
          {hasContent && (
            <>
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
                  setErrors([]);
                }}
                disabled={disabled}
              >
                Clear
              </button>
            </>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="attachment-file-input"
          onChange={onFileInputChange}
          disabled={disabled}
        />
      </div>

      {errors.length > 0 && (
        <div className="attachment-errors">
          {errors.map((err, i) => (
            <div key={i} className="attachment-error">
              <strong>{err.name}</strong> — {err.reason}
            </div>
          ))}
        </div>
      )}

      {showEditor ? (
        <textarea
          className="attachment-textarea"
          placeholder="Paste, type, or drop a file here…"
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

      {dragging && (
        <div className="attachment-drop-overlay" aria-hidden>
          Drop files to attach
        </div>
      )}
    </div>
  );
}
