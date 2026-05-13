/**
 * Operating modes for the LLM Council.
 *
 * Keys MUST match the keys in `backend/modes.py` — the backend keys the
 * orchestration off these strings. Mode `null` means free chat (original
 * behavior, no system prompt, no roles).
 */

export const MODES = [
  {
    key: null,
    label: 'Free Chat',
    short: 'Free Chat',
    description: 'Open-ended council Q&A. No system prompt, no roles.',
  },
  {
    key: 'spec_review',
    label: 'Spec Review',
    short: 'Spec Review',
    description:
      'Critique a product spec. Claude = Architect, Gemini = Critical Reviewer, GPT = Stress Tester.',
  },
  {
    key: 'architecture_debate',
    label: 'Architecture Debate',
    short: 'Architecture',
    description:
      'Two debate rounds with randomized stances (for / against / neutral) before chairman synthesis.',
  },
  {
    key: 'code_review',
    label: 'Code Review',
    short: 'Code Review',
    description:
      'Production code review. Claude = Security & Patterns, Gemini = Performance & Scale, GPT = Edge Cases & Error Handling.',
  },
];

export const DEFAULT_MODE_KEY = null;

export function findMode(key) {
  return MODES.find((m) => m.key === key) || MODES[0];
}
