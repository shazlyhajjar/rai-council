/**
 * Persistent display identities for the council members.
 *
 * The underlying OpenRouter model strings are unchanged — this is a pure
 * display layer applied in Stage 1 tabs, Stage 2 evaluation headers, and
 * the Stage 3 chairman card. The History page uses these too.
 */

const MODEL_IDENTITIES = {
  'anthropic/claude-opus-4.7': {
    name: 'Jarvis Prime',
    subtitle: 'Architect & Drafter',
    color: '#7c3aed',
  },
  'google/gemini-3.1-pro-preview': {
    name: 'Gemini Reviewer',
    subtitle: 'Critical Reviewer',
    color: '#0ea5e9',
  },
  'openai/gpt-5.4': {
    name: 'GPT Challenger',
    subtitle: 'Adversarial Stress Tester',
    color: '#f59e0b',
  },
};

const CHAIRMAN_IDENTITY = {
  name: 'Council Chairman',
  subtitle: 'Synthesis & Verdict',
  color: '#15803d',
};

const FALLBACK = (model) => ({
  name: shortModel(model),
  subtitle: '',
  color: '#6b7280',
});

function shortModel(model) {
  if (!model) return 'Unknown';
  const parts = String(model).split('/');
  return parts[1] || model;
}

/**
 * Resolve an identity for a council-member model id.
 * Returns { name, subtitle, color, model }.
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

export { shortModel };
