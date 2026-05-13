import { useEffect, useRef, useState } from 'react';
import './CopyButton.css';

/**
 * One-click "copy markdown to clipboard" button.
 *
 * Props:
 *   getText:  () => string | string                  — text to copy (function or value)
 *   variant:  "icon" (default) | "labeled"           — small floating icon or full button
 *   label:    string                                  — label text for labeled variant
 *   title:    string                                  — tooltip
 */
export default function CopyButton({ getText, variant = 'icon', label = 'Copy', title }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const handleClick = async (e) => {
    e.stopPropagation();
    const text = typeof getText === 'function' ? getText() : getText;
    if (text == null) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(String(text));
      } else {
        // Fallback for older browsers / non-secure contexts.
        const ta = document.createElement('textarea');
        ta.value = String(text);
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  };

  if (variant === 'labeled') {
    return (
      <button
        type="button"
        className={`copy-button labeled ${copied ? 'copied' : ''}`}
        onClick={handleClick}
        title={title || 'Copy to clipboard'}
        aria-label={title || 'Copy to clipboard'}
      >
        {copied ? (
          <>
            <CheckIcon /> Copied!
          </>
        ) : (
          <>
            <ClipboardIcon /> {label}
          </>
        )}
      </button>
    );
  }

  return (
    <button
      type="button"
      className={`copy-button icon ${copied ? 'copied' : ''}`}
      onClick={handleClick}
      title={title || 'Copy to clipboard'}
      aria-label={title || 'Copy to clipboard'}
    >
      {copied ? <CheckIcon /> : <ClipboardIcon />}
      <span className="copy-button-tooltip">{copied ? 'Copied!' : 'Copy'}</span>
    </button>
  );
}

function ClipboardIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
