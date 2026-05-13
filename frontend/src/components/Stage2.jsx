import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import CopyButton from './CopyButton';
import ModelIdentity, { TabIdentity } from './ModelIdentity';
import { identityFor, tierLabel } from '../modelIdentity';
import './Stage2.css';

function deAnonymizeText(text, labels) {
  if (!labels) return text;

  let result = text;
  Object.entries(labels).forEach(([label, model]) => {
    const id = identityFor(model);
    result = result.replace(new RegExp(label, 'g'), `**${id.name}**`);
  });
  return result;
}

/**
 * One cross-review section — a row of tabs (one per reviewer) and the
 * currently-selected reviewer's evaluation. Anonymized labels in the text
 * are bolded with the reviewed model's display name for readability; the
 * original reviewer evaluated against anonymous A/B/C labels.
 */
function CrossReviewSection({ heading, description, rankings, labels }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!rankings || rankings.length === 0) return null;

  const safeIndex = Math.min(activeTab, rankings.length - 1);
  const active = rankings[safeIndex];

  return (
    <div className="cross-review-section">
      <h4 className="cross-review-heading">{heading}</h4>
      {description && <p className="stage-description">{description}</p>}

      <div className="tabs">
        {rankings.map((rank, index) => (
          <button
            key={index}
            className={`tab identity-tab ${safeIndex === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            <TabIdentity model={rank.model} />
          </button>
        ))}
      </div>

      <div className="tab-content with-copy-button">
        <CopyButton
          getText={() => deAnonymizeText(active.ranking || '', labels)}
          title="Copy this evaluation"
        />
        <ModelIdentity model={active.model} size="card" />
        <div className="ranking-content markdown-content">
          <ReactMarkdown>
            {deAnonymizeText(active.ranking, labels)}
          </ReactMarkdown>
        </div>

        {active.parsed_ranking && active.parsed_ranking.length > 0 && (
          <div className="parsed-ranking">
            <strong>Extracted Ranking:</strong>
            <ol>
              {active.parsed_ranking.map((label, i) => (
                <li key={i}>
                  {labels && labels[label]
                    ? identityFor(labels[label]).name
                    : label}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

function DebateRound2({ rebuttals }) {
  const [activeTab, setActiveTab] = useState(0);
  if (!rebuttals || rebuttals.length === 0) return null;
  const safeIndex = Math.min(activeTab, rebuttals.length - 1);
  const active = rebuttals[safeIndex];

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
            className={`tab identity-tab ${safeIndex === i ? 'active' : ''}`}
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
  if (!rankings || rankings.length === 0) {
    return null;
  }

  if (flow === 'debate') {
    return <DebateRound2 rebuttals={rankings} />;
  }

  // Backend signals full-mesh fallback by stuffing the flat label map under
  // an "all" key. Render the original undivided view in that case.
  const isFullMesh = labelToModel && typeof labelToModel === 'object' && 'all' in labelToModel;

  if (isFullMesh) {
    return (
      <div className="stage stage2">
        <h3 className="stage-title">Stage 2: Peer Rankings</h3>
        <p className="stage-description">
          Cross-team review couldn't run (one team had no successful responses), so
          every surviving model ranked the rest.
        </p>
        <CrossReviewSection
          heading="All responses"
          rankings={rankings}
          labels={labelToModel.all}
        />
        {aggregateRankings && aggregateRankings.length > 0 && (
          <AggregateRankingsBlock rankings={aggregateRankings} />
        )}
      </div>
    );
  }

  const strategistRankings = rankings.filter((r) => r.reviewer_tier === 'strategist');
  const builderRankings = rankings.filter((r) => r.reviewer_tier === 'builder');

  return (
    <div className="stage stage2">
      <h3 className="stage-title">Stage 2: Cross-Team Peer Review</h3>
      <p className="stage-description">
        Each strategist ranked the builders' responses. Each builder ranked the
        strategists'. Neither team reviewed its own — this surfaces blind spots,
        not popularity contests. Anonymized labels (Response A / B / C) are
        shown bolded with the model's display name for readability.
      </p>

      <CrossReviewSection
        heading={`${tierLabel('strategist')} evaluating ${tierLabel('builder')}`}
        rankings={strategistRankings}
        labels={labelToModel?.builders}
      />

      <CrossReviewSection
        heading={`${tierLabel('builder')} evaluating ${tierLabel('strategist')}`}
        rankings={builderRankings}
        labels={labelToModel?.strategists}
      />

      {aggregateRankings && aggregateRankings.length > 0 && (
        <AggregateRankingsBlock rankings={aggregateRankings} />
      )}
    </div>
  );
}

function AggregateRankingsBlock({ rankings }) {
  return (
    <div className="aggregate-rankings">
      <h4>Aggregate Rankings (Cross-Team Street Cred)</h4>
      <p className="stage-description">
        Average rank position across cross-team peer evaluations (lower is better).
        Strategists are scored by the builders' rankings; builders are scored by
        the strategists' rankings.
      </p>
      <div className="aggregate-list">
        {rankings.map((agg, index) => {
          const id = identityFor(agg.model);
          return (
            <div key={index} className="aggregate-item">
              <span className="rank-position">#{index + 1}</span>
              <span className="rank-model" style={{ color: id.color }}>
                {id.name}
              </span>
              <span className="rank-tier-pill">{tierLabel(id.tier)}</span>
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
  );
}
