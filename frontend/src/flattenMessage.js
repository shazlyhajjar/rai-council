/**
 * Flatten an assistant message (stage1/stage2/stage3 + metadata) into a single
 * markdown document. Used by the "Copy All" button on the Chairman synthesis.
 */

import { findMode } from './modes';

function shortName(model) {
  if (!model) return '';
  const parts = String(model).split('/');
  return parts[1] || model;
}

export function flattenAssistantMessage(message) {
  if (!message) return '';

  const parts = [];
  const flow = message?.metadata?.flow;
  const mode = message?.metadata?.mode;
  const isDebate = flow === 'debate';

  const header = isDebate
    ? '# Council Debate'
    : '# Council Response';
  parts.push(header);
  if (mode) {
    parts.push(`_Mode:_ **${findMode(mode).label}**`);
  }

  // Stage 1 — opening responses / round 1
  if (Array.isArray(message.stage1) && message.stage1.length > 0) {
    parts.push(isDebate ? '## Round 1 — Opening Arguments' : '## Stage 1 — Individual Responses');
    for (const r of message.stage1) {
      const tag = r.role
        ? ` (${r.role})`
        : r.stance
        ? ` (stance: ${r.stance})`
        : '';
      parts.push(`### ${shortName(r.model)}${tag}`);
      parts.push((r.response || '').trim());
    }
  }

  // Stage 2 — peer rankings or round 2 rebuttals
  if (Array.isArray(message.stage2) && message.stage2.length > 0) {
    parts.push(isDebate ? '## Round 2 — Rebuttals' : '## Stage 2 — Peer Rankings');
    for (const r of message.stage2) {
      const tag = r.stance ? ` (stance: ${r.stance})` : '';
      const body = r.response ?? r.ranking ?? '';
      parts.push(`### ${shortName(r.model)}${tag}`);
      parts.push(String(body).trim());
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
