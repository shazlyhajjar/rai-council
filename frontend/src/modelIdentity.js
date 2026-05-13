/**
 * Persistent display identities for the 6 council members.
 *
 * The underlying OpenRouter model strings are unchanged — this is a pure
 * display layer applied in Stage 1 tabs, Stage 2 cross-review headers, and
 * the Stage 3 chairman card. The History page uses these too.
 *
 * Each identity carries a `tier` field — "strategist" or "builder" — that
 * drives the Stage 1 tab grouping and the Stage 2 cross-review section
 * labels. Strategists are the original 3 high-level reviewers; builders
 * think like coding agents.
 */

const MODEL_IDENTITIES = {
  // ── Strategists ─────────────────────────────────────────────────
  'anthropic/claude-opus-4.7': {
    name: 'Jarvis Prime',
    subtitle: 'Architect & Drafter',
    color: '#7c3aed',
    tier: 'strategist',
  },
  'google/gemini-3.1-pro-preview': {
    name: 'Gemini Reviewer',
    subtitle: 'Critical Reviewer',
    color: '#0ea5e9',
    tier: 'strategist',
  },
  'openai/gpt-5.4': {
    name: 'GPT Challenger',
    subtitle: 'Adversarial Stress Tester',
    color: '#f59e0b',
    tier: 'strategist',
  },
  // ── Builders ────────────────────────────────────────────────────
  'openai/gpt-5.3-codex': {
    name: 'Codex Builder',
    subtitle: 'Implementation Realist',
    color: '#ef4444',
    tier: 'builder',
  },
  'anthropic/claude-sonnet-4.6': {
    name: 'Claude Builder',
    subtitle: 'Build Verifier',
    color: '#db2777',
    tier: 'builder',
  },
  'google/gemini-3-flash-preview': {
    name: 'Jules Engine',
    subtitle: 'Performance & Feasibility Auditor',
    color: '#14b8a6',
    tier: 'builder',
  },
};

const CHAIRMAN_IDENTITY = {
  name: 'Council Chairman',
  subtitle: 'Synthesis & Verdict',
  color: '#15803d',
  tier: 'chairman',
};

const FALLBACK = (model) => ({
  name: shortModel(model),
  subtitle: '',
  color: '#6b7280',
  tier: 'strategist',
});

function shortModel(model) {
  if (!model) return 'Unknown';
  const parts = String(model).split('/');
  return parts[1] || model;
}

/**
 * Resolve an identity for a council-member model id.
 * Returns { name, subtitle, color, tier, model }.
 */
export function identityFor(model) {
  const id = MODEL_IDENTITIES[model] || FALLBACK(model);
  return { ...id, model };
}

/**
 * Resolve the chairman identity. The model string is preserved alongside
 * so consumers can render a "powered by …" caption underneath.
 */
export function chairmanIdentity(model) {
  return { ...CHAIRMAN_IDENTITY, model };
}

/**
 * Human label for a tier. Used by Stage 1 group headers + Stage 2 section titles.
 */
export function tierLabel(tier) {
  if (tier === 'strategist') return 'Strategists';
  if (tier === 'builder') return 'Builders';
  return '';
}

export { shortModel };
