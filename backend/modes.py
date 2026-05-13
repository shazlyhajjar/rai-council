"""Operating modes for the LLM Council.

Each mode defines:
- A system prompt every model receives.
- A `flow` ("roles" or "debate") that selects the orchestration shape.
- For "roles": a per-provider role assignment (Claude/Gemini/GPT each get a different lens).
- For "debate": a list of stances that are randomly assigned to models on every run.

The provider key is derived from the OpenRouter model id prefix
(`anthropic/claude-opus-4.7` -> `anthropic`). If the council roster ever
adds a model whose prefix is not mapped, that model runs without a role
(its response is still collected, just without role-specific framing).
"""

import random
from typing import Dict, List, Optional


SPEC_REVIEW_SYSTEM_PROMPT = (
    "You are reviewing a product specification for a mobile app. "
    "Look for: missing requirements, ambiguous language, contradictions, "
    "edge cases not covered, assumptions not stated, and gaps between what "
    "the spec promises and what it actually defines. Be thorough and critical."
)

ARCHITECTURE_DEBATE_SYSTEM_PROMPT = (
    "You are debating an architectural decision for a mobile app. "
    "Consider: scalability, maintainability, performance, developer experience, "
    "and whether this decision will still make sense in 2 years. "
    "Take a strong position and defend it with concrete reasoning."
)

CODE_REVIEW_SYSTEM_PROMPT = (
    "You are reviewing code for a production mobile app. "
    "Check for: bugs, security issues, performance problems, missing error "
    "handling, unclear naming, violations of the project's existing patterns, "
    "and anything that will cause problems at scale. Be specific — point to "
    "exact lines or patterns."
)


MODES: Dict[str, Dict] = {
    "spec_review": {
        "label": "Spec Review",
        "description": "Each model reviews a spec through a different lens.",
        "system_prompt": SPEC_REVIEW_SYSTEM_PROMPT,
        "flow": "roles",
        "roles": {
            "anthropic": {
                "name": "Architect",
                "prompt": (
                    "Your specific role is the Architect. Focus on structural "
                    "completeness: are the major components defined? Are their "
                    "boundaries clear? Are the integration points specified? Is "
                    "the data model coherent? Flag anything where the structure "
                    "is implied but never spelled out."
                ),
            },
            "google": {
                "name": "Critical Reviewer",
                "prompt": (
                    "Your specific role is the Critical Reviewer. Hunt for gaps "
                    "and contradictions: requirements that conflict, behaviors "
                    "specified in one section and contradicted in another, "
                    "assumptions presented as facts, language that allows two "
                    "valid interpretations. Be unsparing — every contradiction "
                    "must be named."
                ),
            },
            "openai": {
                "name": "Stress Tester",
                "prompt": (
                    "Your specific role is the Stress Tester. Imagine adversarial "
                    "scenarios: what happens on a flaky network? What if the user "
                    "does the steps in an unexpected order? What if the data is "
                    "malformed? What if two users collide on the same operation? "
                    "Surface every edge case the spec does not address."
                ),
            },
        },
    },
    "architecture_debate": {
        "label": "Architecture Debate",
        "description": "Two debate rounds with randomized stances before synthesis.",
        "system_prompt": ARCHITECTURE_DEBATE_SYSTEM_PROMPT,
        "flow": "debate",
        "stances": ["for", "against", "neutral"],
    },
    "code_review": {
        "label": "Code Review",
        "description": "Multi-lens production code review.",
        "system_prompt": CODE_REVIEW_SYSTEM_PROMPT,
        "flow": "roles",
        "roles": {
            "anthropic": {
                "name": "Security & Patterns",
                "prompt": (
                    "Your specific focus is Security & Patterns. Look for: "
                    "injection risks, auth/authz holes, secret handling, unsafe "
                    "deserialization, and violations of the codebase's existing "
                    "conventions and architectural patterns. Cite specific lines "
                    "or constructs."
                ),
            },
            "google": {
                "name": "Performance & Scale",
                "prompt": (
                    "Your specific focus is Performance & Scale. Look for: N+1 "
                    "queries, blocking I/O on hot paths, memory leaks, "
                    "unnecessary work, missing pagination, unbounded loops, and "
                    "anything that degrades at 100× the current load. Cite "
                    "specific lines or constructs."
                ),
            },
            "openai": {
                "name": "Edge Cases & Error Handling",
                "prompt": (
                    "Your specific focus is Edge Cases & Error Handling. Look "
                    "for: missing null/empty/error branches, swallowed "
                    "exceptions, race conditions, off-by-one errors, "
                    "double-free/double-close, and surprising input "
                    "combinations. Cite specific lines or constructs."
                ),
            },
        },
    },
}


STANCE_PROMPTS = {
    "for": (
        "Your assigned stance: argue FOR the proposal. Make the strongest "
        "possible case in its favor. Concrete reasons only — no hedging."
    ),
    "against": (
        "Your assigned stance: argue AGAINST the proposal. Make the strongest "
        "possible case opposing it. Concrete reasons only — no hedging."
    ),
    "neutral": (
        "Your assigned stance: NEUTRAL. Lay out the strongest arguments on "
        "both sides, flag where the trade-offs depend on context, and surface "
        "the questions that should decide the call."
    ),
}


def get_mode(mode_key: Optional[str]) -> Optional[Dict]:
    """Return the mode definition or None for free chat / unknown key."""
    if not mode_key:
        return None
    return MODES.get(mode_key)


def provider_key(model_id: str) -> str:
    """Provider prefix from a model id ('anthropic/claude-opus-4.7' -> 'anthropic')."""
    return model_id.split("/", 1)[0]


def assign_role(model_id: str, mode_def: Optional[Dict]) -> Optional[Dict]:
    """Role for a model under a `roles`-flow mode, or None."""
    if not mode_def or mode_def.get("flow") != "roles":
        return None
    return mode_def.get("roles", {}).get(provider_key(model_id))


def assign_stances(model_ids: List[str]) -> Dict[str, str]:
    """Randomly assign for/against/neutral across the council each run.

    If there are more models than stances, the extra models cycle through
    the same three labels — keeps the assignment deterministic for the
    rest of the pipeline.
    """
    stances = ["for", "against", "neutral"]
    random.shuffle(stances)
    if len(model_ids) > len(stances):
        repeats = (len(model_ids) // len(stances)) + 1
        stances = (stances * repeats)[: len(model_ids)]
    return {model: stance for model, stance in zip(model_ids, stances)}


def list_modes_for_ui() -> List[Dict]:
    """Public-facing mode metadata for the frontend dropdown."""
    return [
        {"key": key, "label": defn["label"], "description": defn["description"]}
        for key, defn in MODES.items()
    ]
