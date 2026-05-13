import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import CopyButton from './CopyButton';
import ModelIdentity, { TabIdentity } from './ModelIdentity';
import { identityFor } from '../modelIdentity';
import './Stage2.css';

function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) return text;

  let result = text;
  Object.entries(labelToModel).forEach(([label, model]) => {
    const id = identityFor(model);
    result = result.replace(new RegExp(label, 'g'), `**${id.name}**`);
  });
  return result;
}

function DebateRound2({ rebuttals }) {
  const [activeTab, setActiveTab] = useState(0);
  if (!rebuttals || rebuttals.length === 0) return null;
  const active = rebuttals[activeTab];

  return (
    <div className="stage stage2">
      <h3 className="stage-title">Round 2: Rebuttals</h3>
      <p className="stage-description">
        Each model saw the other members' Round 1 arguments and was asked to
        rebut while maintaining its assigned stance.
      </p>

      <div className="tabs">
        {rebuttals.map((r, i) => (
          <button
            key={i}
            className={`tab identity-tab ${activeTab === i ? 'active' : ''}`}
            onClick={() => setActiveTab(i)}
          >
            <TabIdentity
              model={r.model}
              trailing={
                r.stance && (
                  <span className={`role-badge stance stance-${r.stance}`}>
                    {r.stance.toUpperCase()}
                  </span>
                )
              }
            />
          </button>
        ))}
      </div>

      <div className="tab-content with-copy-button">
        <CopyButton getText={() => active.response || ''} title="Copy this rebuttal" />
        <ModelIdentity
          model={active.model}
          size="card"
          trailing={
            active.stance && (
              <span className={`role-badge stance stance-${active.stance} role-badge-inline`}>
                {active.stance.toUpperCase()}
              </span>
            )
          }
        />
        <div className="ranking-content markdown-content">
          <ReactMarkdown>{active.response}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default function Stage2({ rankings, labelToModel, aggregateRankings, flow }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!rankings || rankings.length === 0) {
    return null;
  }

  if (flow === 'debate') {
    return <DebateRound2 rebuttals={rankings} />;
  }

  return (
    <div className="stage stage2">
      <h3 className="stage-title">Stage 2: Peer Rankings</h3>

      <h4>Raw Evaluations</h4>
      <p className="stage-description">
        Each model evaluated all responses (anonymized as Response A, B, C, etc.) and provided rankings.
        Below, model names are shown in <strong>bold</strong> for readability, but the original evaluation used anonymous labels.
      </p>

      <div className="tabs">
        {rankings.map((rank, index) => (
          <button
            key={index}
            className={`tab identity-tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            <TabIdentity model={rank.model} />
          </button>
        ))}
      </div>

      <div className="tab-content with-copy-button">
        <CopyButton
          getText={() => deAnonymizeText(rankings[activeTab].ranking || '', labelToModel)}
          title="Copy this evaluation"
        />
        <ModelIdentity model={rankings[activeTab].model} size="card" />
        <div className="ranking-content markdown-content">
          <ReactMarkdown>
            {deAnonymizeText(rankings[activeTab].ranking, labelToModel)}
          </ReactMarkdown>
        </div>

        {rankings[activeTab].parsed_ranking &&
         rankings[activeTab].parsed_ranking.length > 0 && (
          <div className="parsed-ranking">
            <strong>Extracted Ranking:</strong>
            <ol>
              {rankings[activeTab].parsed_ranking.map((label, i) => (
                <li key={i}>
                  {labelToModel && labelToModel[label]
                    ? labelToModel[label].split('/')[1] || labelToModel[label]
                    : label}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {aggregateRankings && aggregateRankings.length > 0 && (
        <div className="aggregate-rankings">
          <h4>Aggregate Rankings (Street Cred)</h4>
          <p className="stage-description">
            Combined results across all peer evaluations (lower score is better):
          </p>
          <div className="aggregate-list">
            {aggregateRankings.map((agg, index) => {
              const id = identityFor(agg.model);
              return (
                <div key={index} className="aggregate-item">
                  <span className="rank-position">#{index + 1}</span>
                  <span className="rank-model" style={{ color: id.color }}>
                    {id.name}
                  </span>
                  <span className="rank-score">
                    Avg: {agg.average_rank.toFixed(2)}
                  </span>
                  <span className="rank-count">
                    ({agg.rankings_count} votes)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
