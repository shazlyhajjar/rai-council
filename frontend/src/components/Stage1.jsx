import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import CopyButton from './CopyButton';
import ModelIdentity, { TabIdentity } from './ModelIdentity';
import './Stage1.css';

function badgeFor(resp) {
  if (resp.role) return { kind: 'role', label: resp.role };
  if (resp.stance) return { kind: `stance stance-${resp.stance}`, label: resp.stance.toUpperCase() };
  return null;
}

export default function Stage1({ responses, flow }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!responses || responses.length === 0) {
    return null;
  }

  const title = flow === 'debate' ? 'Round 1: Opening Arguments' : 'Stage 1: Individual Responses';
  const active = responses[activeTab];
  const activeBadge = badgeFor(active);

  return (
    <div className="stage stage1">
      <h3 className="stage-title">{title}</h3>

      <div className="tabs">
        {responses.map((resp, index) => {
          const badge = badgeFor(resp);
          return (
            <button
              key={index}
              className={`tab identity-tab ${activeTab === index ? 'active' : ''}`}
              onClick={() => setActiveTab(index)}
            >
              <TabIdentity
                model={resp.model}
                trailing={badge && <span className={`role-badge ${badge.kind}`}>{badge.label}</span>}
              />
            </button>
          );
        })}
      </div>

      <div className="tab-content with-copy-button">
        <CopyButton getText={() => active.response || ''} title="Copy this response" />
        <ModelIdentity
          model={active.model}
          size="card"
          trailing={
            activeBadge ? (
              <span className={`role-badge ${activeBadge.kind} role-badge-inline`}>
                {activeBadge.label}
              </span>
            ) : null
          }
        />
        <div className="response-text markdown-content">
          <ReactMarkdown>{active.response}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
