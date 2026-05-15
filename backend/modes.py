"""Operating modes for the LLM Council.

Each mode defines:
- A system prompt every model receives.
- A `flow` ("roles" or "debate") that selects the orchestration shape.
- For "roles": per-MODEL role assignment. With 6 council members split into
  strategists and builders, roles are keyed by full OpenRouter model id (not
  by provider prefix as in v1) so two models from the same provider can hold
  different roles.
- For "debate": a list of stances that are assigned in a tier-balanced way —
  each stance gets one strategist and one builder so neither team dominates
  any single position.
"""

import random
from typing import Dict, List, Optional

from .config import tier_for


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

SPEC_VERIFY_SYSTEM_PROMPT = (
    "You are performing a systematic verification pass on a product "
    "specification. You do not write essays. You work a fixed checklist and "
    "report findings with exact counts. Precision over prose. Never pad, "
    "never editorialize, never summarize at the end."
)

# The six cross-reference axes. (name, what to check). The N/A escape hatch is
# baked into the rendered prompt so a spec that lacks a structural element
# doesn't force fabricated zero-count reports.
SPEC_VERIFY_XREF_AXES = [
    (
        "BEHAVIORS → DATA CONTRACTS",
        "For every numbered behavior, verify it references fields that actually "
        "exist in the data contracts section. Flag any behavior that references "
        "a field name, type, or endpoint not defined in the contracts.",
    ),
    (
        "STATES → TRANSITIONS",
        "For every defined state, verify there is at least one defined "
        "transition INTO that state and at least one transition OUT. Flag "
        "orphan states (no entry) and terminal states (no exit) that aren't "
        "explicitly marked as terminal.",
    ),
    (
        "API ENDPOINTS → CONSUMERS",
        "For every field in every API response schema, verify at least one "
        "behavior or rendering rule consumes it (flag dead fields). For every "
        "field a behavior reads, verify the API actually provides it.",
    ),
    (
        "VISUAL SPECS → DATA SOURCES",
        "For every visual element that displays dynamic data, verify the data "
        "source is defined in the contracts. Flag any visual that references "
        "data with no specified origin.",
    ),
    (
        "CROSS-REFERENCES",
        "For every “see §X” or “per §X” reference, verify the "
        "referenced section actually says what the referencing section claims "
        "it says. Flag mismatches.",
    ),
    (
        "TRAPS → BEHAVIORS",
        "For every trap/constraint, verify at least one behavior enforces it. "
        "Flag unenforceable traps.",
    ),
]

# Fix Verification statuses (adjustment #3 — AMBIGUOUS added so a model isn't
# forced to miscategorize a vague finding or judgment-dependent fix).
SPEC_VERIFY_FIX_STATUSES = [
    "RESOLVED",
    "PARTIALLY RESOLVED",
    "NOT RESOLVED",
    "NEW ISSUE CREATED",
    "AMBIGUOUS",
]


def build_spec_verify_xref_prompt() -> str:
    """The structured cross-reference checklist every model receives."""
    axes_block = "\n\n".join(
        f"{i + 1}. {name}\n   {check}"
        for i, (name, check) in enumerate(SPEC_VERIFY_XREF_AXES)
    )
    return (
        f"Verify the specification by working through these "
        f"{len(SPEC_VERIFY_XREF_AXES)} cross-reference axes IN ORDER. For each "
        f"axis you systematically cross-reference one section against another "
        f"— you do not skim for whatever jumps out.\n\n"
        f"{axes_block}\n\n"
        f"OUTPUT FORMAT — for EACH axis, in order, output exactly:\n\n"
        f"[AXIS NAME]: <N> items checked, <M> issues found\n"
        f"- <specific issue: name the exact behavior/field/state/section>\n"
        f"- <next issue>\n\n"
        f"Rules:\n"
        f"- If an axis has zero issues, still report the count: "
        f"“[AXIS NAME]: 14 items checked, 0 issues found”.\n"
        f"- If the spec does not contain the structural element an axis "
        f"targets (e.g. no numbered behaviors, no state machine, no API "
        f"schemas), report exactly: “[AXIS NAME]: N/A — this spec has no "
        f"<element>” and move on. Do NOT fabricate checks to fill the axis.\n"
        f"- No introduction, no conclusion, no prose outside the per-axis "
        f"format. Start directly with axis 1."
    )


def build_spec_verify_fix_prompt(previous_findings: str) -> str:
    """The fix-verification checklist. `previous_findings` is pasted by the user."""
    statuses = " | ".join(SPEC_VERIFY_FIX_STATUSES)
    findings = (previous_findings or "").strip() or "(no previous findings were provided)"
    return (
        f"You are verifying that fixes were correctly applied. You are given "
        f"(1) the UPDATED spec [in the message below] and (2) the list of "
        f"PREVIOUS FINDINGS here:\n\n"
        f"--- PREVIOUS FINDINGS ---\n{findings}\n--- END PREVIOUS FINDINGS ---\n\n"
        f"For EACH finding, verify three things against the updated spec:\n"
        f"(a) the fix is correctly applied\n"
        f"(b) the fix does not contradict anything in adjacent sections\n"
        f"(c) the fix did not create new gaps\n\n"
        f"OUTPUT FORMAT — one block per finding, in the order the findings "
        f"were listed:\n\n"
        f"FINDING <n>: <one-line restatement of the original finding>\n"
        f"STATUS: <{statuses}>\n"
        f"DETAIL: <REQUIRED unless STATUS is RESOLVED — explain what is still "
        f"wrong, what new issue the fix created, or precisely why it is "
        f"ambiguous to verify>\n\n"
        f"Rules:\n"
        f"- AMBIGUOUS means the original finding was too vague to verify, or "
        f"the fix is judgment-dependent and you cannot say objectively whether "
        f"it resolves the finding. Use it instead of guessing.\n"
        f"- Do NOT re-review sections that were not part of the original "
        f"findings. This is not a fresh review.\n"
        f"- Do NOT invent findings that were not in the list. The only "
        f"exception: if a fix to a listed finding directly created a new "
        f"problem, record it under that finding as NEW ISSUE CREATED.\n"
        f"- No essay. No summary. Start directly with FINDING 1."
    )


# Per-mode role prompts, keyed by full OpenRouter model id. Each tier has 3
# slots; strategists set the lens, builders set the implementation reality.
MODES: Dict[str, Dict] = {
    "spec_review": {
        "label": "Spec Review",
        "description": "Each model reviews a spec through a different lens. Strategists set the lens, builders flag what would block implementation.",
        "system_prompt": SPEC_REVIEW_SYSTEM_PROMPT,
        "flow": "roles",
        "roles": {
            # ── Strategists ────────────────────────────────────────────
            "anthropic/claude-opus-4.7": {
                "name": "Architect",
                "prompt": (
                    "Your specific role is the Architect. Focus on structural "
                    "completeness: are the major components defined? Are their "
                    "boundaries clear? Are the integration points specified? Is "
                    "the data model coherent? Flag anything where the structure "
                    "is implied but never spelled out."
                ),
            },
            "google/gemini-3.1-pro-preview": {
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
            "openai/gpt-5.4": {
                "name": "Stress Tester",
                "prompt": (
                    "Your specific role is the Stress Tester. Imagine adversarial "
                    "scenarios: what happens on a flaky network? What if the user "
                    "does the steps in an unexpected order? What if the data is "
                    "malformed? What if two users collide on the same operation? "
                    "Surface every edge case the spec does not address."
                ),
            },
            # ── Builders ───────────────────────────────────────────────
            "openai/gpt-5.3-codex": {
                "name": "Implementation Realist",
                "prompt": (
                    "Your specific role is the Implementation Realist. Read this "
                    "spec as the developer who has to build it. If you opened a "
                    "ticket with 'implement this' right now, what would block "
                    "you from writing the first commit? Look for: terms "
                    "introduced but never defined, happy-path flows with no "
                    "input-validation story, behaviors mentioned in passing "
                    "with no place to live in the architecture. Point at the "
                    "exact phrase that's ambiguous and say what's missing to "
                    "make it actionable."
                ),
            },
            "anthropic/claude-sonnet-4.6": {
                "name": "Build Verifier",
                "prompt": (
                    "Your specific role is the Build Verifier. Ask 'can I write "
                    "tests against this spec?' Are inputs and outputs of each "
                    "capability fully specified so I can write assertions? Are "
                    "component boundaries crisp enough that I know where to "
                    "mock? Is the state machine drawn out, or will I discover "
                    "it by trial and error? Flag every gap that would force me "
                    "to make undocumented decisions during build."
                ),
            },
            "google/gemini-3-flash-preview": {
                "name": "Feasibility Auditor",
                "prompt": (
                    "Your specific role is the Feasibility Auditor. Look at "
                    "performance assumptions (latency targets, payload sizes, "
                    "request volumes), dependencies that must exist before "
                    "this can be built (other services, migrations, third-"
                    "party access), and build sequencing — what has to ship "
                    "first. Where would this collapse at 10× scale? Surface "
                    "every implicit assumption the spec is leaning on without "
                    "naming."
                ),
            },
        },
    },
    "architecture_debate": {
        "label": "Architecture Debate",
        "description": "Two debate rounds with stances assigned across both teams (each stance held by one strategist + one builder) before chairman synthesis.",
        "system_prompt": ARCHITECTURE_DEBATE_SYSTEM_PROMPT,
        "flow": "debate",
        "stances": ["for", "against", "neutral"],
    },
    "code_review": {
        "label": "Code Review",
        "description": "Multi-lens production code review. Strategists pick at correctness and design, builders flag what would block extending or testing.",
        "system_prompt": CODE_REVIEW_SYSTEM_PROMPT,
        "flow": "roles",
        "roles": {
            # ── Strategists ────────────────────────────────────────────
            "anthropic/claude-opus-4.7": {
                "name": "Security & Patterns",
                "prompt": (
                    "Your specific focus is Security & Patterns. Look for: "
                    "injection risks, auth/authz holes, secret handling, unsafe "
                    "deserialization, and violations of the codebase's existing "
                    "conventions and architectural patterns. Cite specific lines "
                    "or constructs."
                ),
            },
            "google/gemini-3.1-pro-preview": {
                "name": "Performance & Scale",
                "prompt": (
                    "Your specific focus is Performance & Scale. Look for: N+1 "
                    "queries, blocking I/O on hot paths, memory leaks, "
                    "unnecessary work, missing pagination, unbounded loops, and "
                    "anything that degrades at 100× the current load. Cite "
                    "specific lines or constructs."
                ),
            },
            "openai/gpt-5.4": {
                "name": "Edge Cases & Error Handling",
                "prompt": (
                    "Your specific focus is Edge Cases & Error Handling. Look "
                    "for: missing null/empty/error branches, swallowed "
                    "exceptions, race conditions, off-by-one errors, "
                    "double-free/double-close, and surprising input "
                    "combinations. Cite specific lines or constructs."
                ),
            },
            # ── Builders ───────────────────────────────────────────────
            "openai/gpt-5.3-codex": {
                "name": "Extensibility Realist",
                "prompt": (
                    "Your specific focus is Extensibility Realism. You are the "
                    "developer who has to extend this code next week. Flag "
                    "every place where existing patterns are unclear, where "
                    "naming makes you guess intent, where understanding the "
                    "contract requires reading three files. Point at the "
                    "specific lines that would slow down the next implementer."
                ),
            },
            "anthropic/claude-sonnet-4.6": {
                "name": "Test Seam Verifier",
                "prompt": (
                    "Your specific focus is Test Seams. You are the engineer "
                    "asked to write tests for this code as-is. Where are the "
                    "seams unclear? Which functions take inputs that aren't "
                    "fully specified so you can't draft a test matrix? Where "
                    "does behavior depend on global or hidden state that won't "
                    "surface in unit tests? Where would you have to refactor "
                    "just to test it?"
                ),
            },
            "google/gemini-3-flash-preview": {
                "name": "Async & Dependency Auditor",
                "prompt": (
                    "Your specific focus is Async, Performance & Dependency "
                    "Risk. Look for: blocking I/O in async paths, sequential "
                    "awaits that should be parallel, hidden N+1 patterns, "
                    "dependency surfaces that grew without a barrier, "
                    "build-order coupling (one module silently requires "
                    "another to initialize first). Be specific — cite lines."
                ),
            },
        },
    },
    "spec_verify": {
        "label": "Spec Verify",
        "description": (
            "Systematic verification. Cross-Reference Review walks 6 fixed "
            "axes and reports counts + issues by axis (no essays). Fix "
            "Verification checks a prior findings list against the updated "
            "spec and returns a per-finding scorecard."
        ),
        "system_prompt": SPEC_VERIFY_SYSTEM_PROMPT,
        "flow": "spec_verify",
        # No `roles` key on purpose — every model runs the SAME structured
        # checklist with an empty role prompt (no "be the Architect" nudge
        # layered on top of "check axis 3").
        "sub_modes": ["cross_reference", "fix_verification"],
        "default_sub_mode": "cross_reference",
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


def assign_role(model_id: str, mode_def: Optional[Dict]) -> Optional[Dict]:
    """Role for a model under a `roles`-flow mode, or None.

    Keyed by full model id (e.g. 'anthropic/claude-sonnet-4.6') so two models
    from the same provider can hold different roles.
    """
    if not mode_def or mode_def.get("flow") != "roles":
        return None
    return mode_def.get("roles", {}).get(model_id)


def assign_stances(model_ids: List[str]) -> Dict[str, str]:
    """Assign for/against/neutral stances across the council.

    With the canonical 3 strategists + 3 builders roster, each stance gets one
    strategist and one builder — neither team dominates a single position.
    The order within each team is randomized per call so debates don't become
    predictable.

    Falls back to the original cycle behavior if the roster isn't balanced 3+3
    (e.g. a model failed earlier and got filtered out).
    """
    stances = ["for", "against", "neutral"]

    strategists = [m for m in model_ids if tier_for(m) == "strategist"]
    builders = [m for m in model_ids if tier_for(m) == "builder"]

    if len(strategists) == 3 and len(builders) == 3:
        random.shuffle(strategists)
        random.shuffle(builders)
        balanced: Dict[str, str] = {}
        for stance, s_model, b_model in zip(stances, strategists, builders):
            balanced[s_model] = stance
            balanced[b_model] = stance
        return balanced

    # Off-spec roster — cycle the three stances across whatever models we have.
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
