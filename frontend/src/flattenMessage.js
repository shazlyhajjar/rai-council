/**
 * Flatten an assistant message (stage1/stage2/stage3 + metadata) into a single
 * markdown document. Used by the "Copy All" button on the Chairman synthesis.
 */

import { findMode } from './modes';
import { identityFor, tierLabel } from './modelIdentity';

function shortName(model) {
  if (!model) return '';
  const parts = String(model).split('/');
  return parts[1] || model;
}

function tierOf(model) {
  const t = identityFor(model).tier;
  return t === 'builder' ? 'builder' : 'strategist';
}

export function flattenAssistantMessage(message) {
  if (!message) return '';

  const parts = [];
  const flow = message?.metadata?.flow;
  const mode = message?.metadata?.mode;
  const isDebate = flow === 'debate';
  const labelToModel = message?.metadata?.label_to_model;
  const isFullMeshFallback =
    labelToModel && typeof labelToModel === 'object' && 'all' in labelToModel;

  const header = isDebate
    ? '# Council Debate'
    : '# Council Response';
  parts.push(header);
  if (mode) {
    parts.push(`_Mode:_ **${findMode(mode).label}**`);
  }

  // Stage 1 — opening responses / round 1, grouped by tier (non-debate) or
  // flat (debate; stance grouping matters more there).
  if (Array.isArray(message.stage1) && message.stage1.length > 0) {
    parts.push(isDebate ? '## Round 1 — Opening Arguments' : '## Stage 1 — Individual Responses');

    if (isDebate) {
      for (const r of message.stage1) {
        const tag = r.stance ? ` (stance: ${r.stance}, tier: ${tierOf(r.model)})` : '';
        parts.push(`### ${shortName(r.model)}${tag}`);
        parts.push((r.response || '').trim());
      }
    } else {
      const strategists = message.stage1.filter((r) => tierOf(r.model) === 'strategist');
      const builders = message.stage1.filter((r) => tierOf(r.model) === 'builder');
      for (const [tier, items] of [['strategist', strategists], ['builder', builders]]) {
        if (items.length === 0) continue;
        parts.push(`### ${tierLabel(tier)}`);
        for (const r of items) {
          const tag = r.role ? ` (${r.role})` : '';
          parts.push(`#### ${shortName(r.model)}${tag}`);
          parts.push((r.response || '').trim());
        }
      }
    }
  }

  // Stage 2 — peer rankings or round 2 rebuttals.
  if (Array.isArray(message.stage2) && message.stage2.length > 0) {
    if (isDebate) {
      parts.push('## Round 2 — Rebuttals');
      for (const r of message.stage2) {
        const tag = r.stance ? ` (stance: ${r.stance}, tier: ${tierOf(r.model)})` : '';
        parts.push(`### ${shortName(r.model)}${tag}`);
        parts.push(String(r.response ?? '').trim());
      }
    } else if (isFullMeshFallback) {
      parts.push('## Stage 2 — Peer Rankings');
      for (const r of message.stage2) {
        parts.push(`### ${shortName(r.model)}`);
        parts.push(String(r.ranking ?? '').trim());
      }
    } else {
      parts.push('## Stage 2 — Cross-Team Peer Review');
      const strats = message.stage2.filter((r) => r.reviewer_tier === 'strategist');
      const builds = message.stage2.filter((r) => r.reviewer_tier === 'builder');

      if (strats.length > 0) {
        parts.push(`### ${tierLabel('strategist')} evaluating ${tierLabel('builder')}`);
        for (const r of strats) {
          parts.push(`#### ${shortName(r.model)}`);
          parts.push(String(r.ranking ?? '').trim());
        }
      }
      if (builds.length > 0) {
        parts.push(`### ${tierLabel('builder')} evaluating ${tierLabel('strategist')}`);
        for (const r of builds) {
          parts.push(`#### ${shortName(r.model)}`);
          parts.push(String(r.ranking ?? '').trim());
        }
      }
    }

    // Aggregate rankings (only relevant for non-debate flow)
    const agg = message?.metadata?.aggregate_rankings;
    if (!isDebate && Array.isArray(agg) && agg.length > 0) {
      parts.push('### Aggregate Rankings');
      agg.forEach((a, i) => {
        parts.push(`${i + 1}. **${shortName(a.model)}** — avg ${a.average_rank.toFixed(2)} (${a.rankings_count} votes)`);
      });
    }
  }

  // Stage 3 — chairman
  if (message.stage3?.response) {
    parts.push(isDebate ? '## Chairman Verdict' : '## Stage 3 — Final Council Answer');
    parts.push(`_Chairman:_ ${shortName(message.stage3.model)}`);
    parts.push(message.stage3.response.trim());
  }

  return parts.join('\n\n');
}
