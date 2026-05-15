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
    description: 'Open-ended council Q&A. All 6 models respond; cross-team peer review still applies.',
  },
  {
    key: 'spec_review',
    label: 'Spec Review',
    short: 'Spec Review',
    description:
      'Critique a product spec. Strategists set the lens (Architect / Critical Reviewer / Stress Tester); Builders flag what would block implementation (Codex Builder / Claude Builder / Jules Engine).',
  },
  {
    key: 'architecture_debate',
    label: 'Architecture Debate',
    short: 'Architecture',
    description:
      'Two debate rounds. Each stance (for / against / neutral) is held by one strategist and one builder, so neither team dominates a single position.',
  },
  {
    key: 'code_review',
    label: 'Code Review',
    short: 'Code Review',
    description:
      'Production code review. Strategists pick at correctness and design (Security & Patterns / Performance & Scale / Edge Cases). Builders flag what would block extending or testing (Extensibility / Test Seams / Async & Deps).',
  },
  {
    key: 'spec_verify',
    label: 'Spec Verify',
    short: 'Spec Verify',
    description:
      'Systematic verification. Cross-Reference Review walks 6 fixed axes and reports counts + issues by axis (no essays). Fix Verification checks a prior findings list against the updated spec and returns a per-finding scorecard.',
    subModes: [
      { key: 'cross_reference', label: 'Cross-Reference Review' },
      { key: 'fix_verification', label: 'Fix Verification' },
    ],
    defaultSubMode: 'cross_reference',
  },
];

export const DEFAULT_SUB_MODE = 'cross_reference';

export const DEFAULT_MODE_KEY = null;

export function findMode(key) {
  return MODES.find((m) => m.key === key) || MODES[0];
}
