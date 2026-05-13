import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import CopyButton from './CopyButton';
import ModelIdentity, { TabIdentity } from './ModelIdentity';
import { identityFor, tierLabel } from '../modelIdentity';
import './Stage1.css';

function badgeFor(resp) {
  if (resp.role) return { kind: 'role', label: resp.role };
  if (resp.stance) return { kind: `stance stance-${resp.stance}`, label: resp.stance.toUpperCase() };
  return null;
}

/**
 * Partition responses into ordered (tier, [{response, index}]) groups so the
 * tab strip can render Strategists above Builders without losing the global
 * index that drives `active` selection.
 */
function groupByTier(responses) {
  const groups = { strategist: [], builder: [] };
  responses.forEach((r, idx) => {
    const tier = identityFor(r.model).tier === 'builder' ? 'builder' : 'strategist';
    groups[tier].push({ r, idx });
  });
  return [
    { tier: 'strategist', items: groups.strategist },
    { tier: 'builder', items: groups.builder },
  ].filter((g) => g.items.length > 0);
}

export default function Stage1({ responses, flow }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!responses || responses.length === 0) {
    return null;
  }

  const title = flow === 'debate' ? 'Round 1: Opening Arguments' : 'Stage 1: Individual Responses';
  const safeIndex = Math.min(activeTab, responses.length - 1);
  const active = responses[safeIndex];
  const activeBadge = badgeFor(active);
  const groups = groupByTier(responses);

  return (
    <div className="stage stage1">
      <h3 className="stage-title">{title}</h3>

      <div className="tier-groups">
        {groups.map((group) => (
          <div key={group.tier} className={`tier-group tier-${group.tier}`}>
            <div className="tier-group-header">{tierLabel(group.tier)}</div>
            <div className="tabs">
              {group.items.map(({ r, idx }) => {
                const badge = badgeFor(r);
                return (
                  <button
                    key={idx}
                    className={`tab identity-tab ${safeIndex === idx ? 'active' : ''}`}
                    onClick={() => setActiveTab(idx)}
                  >
                    <TabIdentity
                      model={r.model}
                      trailing={badge && <span className={`role-badge ${badge.kind}`}>{badge.label}</span>}
                    />
                  </button>
                );
              })}
            </div>
          </div>
        ))}
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
