"""3-stage LLM Council orchestration (6-member version, post-DR/v2).

Stage 1 — every council member responds (role-aware in roles modes).
Stage 2 — cross-team peer review: strategists rank builders, builders rank
          strategists. One ranking call per reviewer, 6 calls total.
Stage 3 — chairman synthesizes with explicit strategist/builder grouping.
"""

from typing import List, Dict, Any, Optional, Tuple
from .openrouter import (
    query_models_parallel,
    query_models_parallel_per_messages,
    query_model,
)
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL, tier_for
from .context import get_brief
from .modes import (
    get_mode,
    assign_role,
    assign_stances,
    STANCE_PROMPTS,
)


def _compose_system(task_system: Optional[str] = None) -> str:
    """Prepend the auto-loaded RAI brief to a task-specific system prompt.

    Returns the combined string for use as a system message. Returns '' if
    neither the brief nor the task system content is present.
    """
    brief = get_brief()
    parts: List[str] = []
    if brief and brief.strip():
        parts.append(
            "# PROJECT CONTEXT (auto-loaded for every council member)\n\n"
            f"{brief.strip()}"
        )
    if task_system and task_system.strip():
        parts.append(f"# YOUR TASK\n\n{task_system.strip()}")
    return "\n\n---\n\n".join(parts)


def _system_message(task_system: Optional[str] = None) -> List[Dict[str, str]]:
    """Return a [{role: system, content: ...}] list, or [] if no content."""
    content = _compose_system(task_system)
    return [{"role": "system", "content": content}] if content else []


def _build_role_messages(user_query: str, mode_def: Dict, model: str) -> List[Dict[str, str]]:
    """Compose messages for a `roles`-flow model: brief + system + role + user query."""
    role = assign_role(model, mode_def) or {}
    system_blocks = [mode_def["system_prompt"]]
    if role.get("prompt"):
        system_blocks.append(role["prompt"])
    task_system = "\n\n".join(system_blocks)
    return [
        {"role": "system", "content": _compose_system(task_system)},
        {"role": "user", "content": user_query},
    ]


def _build_debate_round1_messages(
    user_query: str, mode_def: Dict, stance: str
) -> List[Dict[str, str]]:
    """Compose messages for debate round 1: brief + system + stance + user query."""
    task_system = "\n\n".join([mode_def["system_prompt"], STANCE_PROMPTS[stance]])
    return [
        {"role": "system", "content": _compose_system(task_system)},
        {"role": "user", "content": user_query},
    ]


def _build_debate_round2_messages(
    user_query: str,
    mode_def: Dict,
    stance: str,
    own_round1: str,
    other_round1: List[Tuple[str, str, str]],
) -> List[Dict[str, str]]:
    """Compose messages for debate round 2.

    `other_round1` is a list of (model_label, stance, response) for the
    OTHER council members so this model can rebut.
    """
    others_text = "\n\n".join(
        f"{label} (arguing {st}):\n{resp}" for label, st, resp in other_round1
    )
    user_prompt = (
        f"Original question:\n{user_query}\n\n"
        f"Your round 1 argument (you are arguing {stance}):\n{own_round1}\n\n"
        f"The other council members argued:\n\n{others_text}\n\n"
        "Round 2: rebut the strongest counter-arguments and sharpen your own "
        f"case. Maintain your stance ({stance}). Be concrete and specific."
    )
    task_system = "\n\n".join([mode_def["system_prompt"], STANCE_PROMPTS[stance]])
    return [
        {"role": "system", "content": _compose_system(task_system)},
        {"role": "user", "content": user_prompt},
    ]


async def stage1_collect_responses(
    user_query: str,
    mode_def: Optional[Dict] = None,
) -> List[Dict[str, Any]]:
    """Stage 1: collect responses, mode-aware.

    - Free chat (mode_def is None): plain user query, no system prompt.
    - Roles mode: each model gets a unique role prompt.
    - Debate mode: this function is NOT used — see `debate_round1` below.
    """
    if mode_def and mode_def.get("flow") == "roles":
        per_model_messages = {
            model: _build_role_messages(user_query, mode_def, model)
            for model in COUNCIL_MODELS
        }
        responses = await query_models_parallel_per_messages(per_model_messages)

        results: List[Dict[str, Any]] = []
        for model, response in responses.items():
            if response is None:
                continue
            role = assign_role(model, mode_def) or {}
            results.append(
                {
                    "model": model,
                    "response": response.get("content", ""),
                    "role": role.get("name"),
                    "tier": tier_for(model),
                }
            )
        return results

    # Free chat path — original behavior, but the auto-loaded RAI brief is
    # still injected as a system message so every model sees project context.
    messages = _system_message() + [{"role": "user", "content": user_query}]
    responses = await query_models_parallel(COUNCIL_MODELS, messages)
    return [
        {
            "model": model,
            "response": response.get("content", ""),
            "tier": tier_for(model),
        }
        for model, response in responses.items()
        if response is not None
    ]


async def debate_round1(
    user_query: str,
    mode_def: Dict,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Architecture Debate round 1 — tier-balanced stances, parallel.

    Returns (results, stance_map). `results` is shaped like stage1 so the
    frontend can reuse the same renderer; each entry carries `stance` + `tier`.
    """
    stance_map = assign_stances(COUNCIL_MODELS)
    per_model_messages = {
        model: _build_debate_round1_messages(user_query, mode_def, stance_map[model])
        for model in COUNCIL_MODELS
    }
    responses = await query_models_parallel_per_messages(per_model_messages)

    results: List[Dict[str, Any]] = []
    for model, response in responses.items():
        if response is None:
            continue
        results.append(
            {
                "model": model,
                "response": response.get("content", ""),
                "stance": stance_map[model],
                "tier": tier_for(model),
            }
        )
    return results, stance_map


async def debate_round2(
    user_query: str,
    mode_def: Dict,
    round1: List[Dict[str, Any]],
    stance_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Architecture Debate round 2 — each model rebuts the others."""
    by_model = {r["model"]: r for r in round1}

    per_model_messages: Dict[str, List[Dict[str, str]]] = {}
    for r in round1:
        model = r["model"]
        stance = stance_map[model]
        others = [
            (other["model"].split("/", 1)[-1], stance_map[other["model"]], other["response"])
            for other in round1
            if other["model"] != model
        ]
        per_model_messages[model] = _build_debate_round2_messages(
            user_query=user_query,
            mode_def=mode_def,
            stance=stance,
            own_round1=by_model[model]["response"],
            other_round1=others,
        )

    responses = await query_models_parallel_per_messages(per_model_messages)

    results: List[Dict[str, Any]] = []
    for model, response in responses.items():
        if response is None:
            continue
        results.append(
            {
                "model": model,
                "response": response.get("content", ""),
                "stance": stance_map[model],
                "tier": tier_for(model),
            }
        )
    return results


_RANKING_FORMAT_INSTRUCTIONS = """Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly through the lens of your own role.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""


def _build_cross_review_prompt(
    user_query: str, responses_text: str, reviewed_tier_label: str
) -> str:
    """Prompt for a single cross-review ranking call.

    `reviewed_tier_label` is "BUILDER" or "STRATEGIST" — appears in the prompt
    so the reviewer knows whose work they're rating.
    """
    return f"""You are evaluating {reviewed_tier_label} responses to the following question.

Question: {user_query}

Here are the {reviewed_tier_label.lower()} responses, anonymized:

{responses_text}

{_RANKING_FORMAT_INSTRUCTIONS}"""


async def _stage2_cross_review(
    user_query: str,
    strategist_responses: List[Dict[str, Any]],
    builder_responses: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, str]]]:
    """Run the cross-review pattern: each strategist ranks the builders, each
    builder ranks the strategists. 6 parallel ranking calls total.
    """
    # Anonymize each team independently with labels A, B, C…
    builder_labels = [chr(65 + i) for i in range(len(builder_responses))]
    strategist_labels = [chr(65 + i) for i in range(len(strategist_responses))]

    builders_label_to_model = {
        f"Response {label}": r["model"]
        for label, r in zip(builder_labels, builder_responses)
    }
    strategists_label_to_model = {
        f"Response {label}": r["model"]
        for label, r in zip(strategist_labels, strategist_responses)
    }

    builders_text = "\n\n".join(
        f"Response {label}:\n{r['response']}"
        for label, r in zip(builder_labels, builder_responses)
    )
    strategists_text = "\n\n".join(
        f"Response {label}:\n{r['response']}"
        for label, r in zip(strategist_labels, strategist_responses)
    )

    # Strategists rank builders; builders rank strategists.
    strategist_prompt = _build_cross_review_prompt(user_query, builders_text, "BUILDER")
    builder_prompt = _build_cross_review_prompt(user_query, strategists_text, "STRATEGIST")

    per_model_messages: Dict[str, List[Dict[str, str]]] = {}
    for r in strategist_responses:
        per_model_messages[r["model"]] = _system_message() + [
            {"role": "user", "content": strategist_prompt}
        ]
    for r in builder_responses:
        per_model_messages[r["model"]] = _system_message() + [
            {"role": "user", "content": builder_prompt}
        ]

    responses = await query_models_parallel_per_messages(per_model_messages)

    stage2_results: List[Dict[str, Any]] = []
    for model, response in responses.items():
        if response is None:
            continue
        full_text = response.get("content", "")
        stage2_results.append(
            {
                "model": model,
                "reviewer_tier": tier_for(model),
                "ranking": full_text,
                "parsed_ranking": parse_ranking_from_text(full_text),
            }
        )

    label_to_model = {
        "builders": builders_label_to_model,
        "strategists": strategists_label_to_model,
    }
    return stage2_results, label_to_model


async def _stage2_full_mesh(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, str]]]:
    """Original full-mesh peer ranking — every model ranks all responses.

    Used as a fallback when cross-review can't run (one tier ended up empty
    because every model in that tier failed). Wraps the flat label_to_model
    in the new dict-of-dicts shape under an "all" key so callers can handle
    both modes uniformly.
    """
    labels = [chr(65 + i) for i in range(len(stage1_results))]

    label_to_model = {
        f"Response {label}": r["model"]
        for label, r in zip(labels, stage1_results)
    }

    responses_text = "\n\n".join(
        f"Response {label}:\n{r['response']}"
        for label, r in zip(labels, stage1_results)
    )

    ranking_prompt = (
        f"You are evaluating different responses to the following question.\n\n"
        f"Question: {user_query}\n\n"
        f"Here are the responses from different models (anonymized):\n\n"
        f"{responses_text}\n\n"
        f"{_RANKING_FORMAT_INSTRUCTIONS}"
    )

    messages = _system_message() + [{"role": "user", "content": ranking_prompt}]
    responses = await query_models_parallel(
        [r["model"] for r in stage1_results], messages
    )

    stage2_results: List[Dict[str, Any]] = []
    for model, response in responses.items():
        if response is None:
            continue
        full_text = response.get("content", "")
        stage2_results.append(
            {
                "model": model,
                "reviewer_tier": tier_for(model),
                "ranking": full_text,
                "parsed_ranking": parse_ranking_from_text(full_text),
            }
        )

    return stage2_results, {"all": label_to_model}


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, str]]]:
    """Stage 2: cross-team peer review.

    Strategists rank the builders' responses; builders rank the strategists'.
    Returns (rankings, label_to_model) where label_to_model is shaped as
    `{"builders": {"Response A": model_id, …}, "strategists": {…}}`.

    If one tier ended up empty (every model in it failed Stage 1), falls back
    to full-mesh ranking over the survivors and returns label_to_model as
    `{"all": {…}}`.
    """
    strategists = [r for r in stage1_results if tier_for(r["model"]) == "strategist"]
    builders = [r for r in stage1_results if tier_for(r["model"]) == "builder"]

    if strategists and builders:
        return await _stage2_cross_review(user_query, strategists, builders)
    return await _stage2_full_mesh(user_query, stage1_results)


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    mode_def: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Stage 3 (roles / free-chat): Chairman synthesizes with team grouping."""

    strategists = [r for r in stage1_results if tier_for(r["model"]) == "strategist"]
    builders = [r for r in stage1_results if tier_for(r["model"]) == "builder"]

    strats_reviewing_builders = [
        r for r in stage2_results if r.get("reviewer_tier") == "strategist"
    ]
    builders_reviewing_strats = [
        r for r in stage2_results if r.get("reviewer_tier") == "builder"
    ]

    def _fmt_responses(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "(no responses from this team)"
        return "\n\n".join(
            f"Model: {r['model']}"
            + (f" (role: {r['role']})" if r.get("role") else "")
            + f"\nResponse: {r['response']}"
            for r in items
        )

    def _fmt_rankings(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "(no cross-review from this team)"
        return "\n\n".join(
            f"Model: {r['model']}\nReview: {r['ranking']}" for r in items
        )

    mode_label = (mode_def or {}).get("label", "Council")

    # If only one tier responded (degenerate / fallback mode), drop back to the
    # original undivided chairman prompt — keeps the output coherent.
    if not strategists or not builders:
        stage1_text = "\n\n".join(
            f"Model: {r['model']}"
            + (f" (role: {r['role']})" if r.get("role") else "")
            + f"\nResponse: {r['response']}"
            for r in stage1_results
        )
        stage2_text = "\n\n".join(
            f"Model: {r['model']}\nRanking: {r['ranking']}" for r in stage2_results
        )
        chairman_prompt = (
            f"You are the Chairman of an LLM Council.\n\n"
            f"Mode: {mode_label}\n\n"
            f"Original Question: {user_query}\n\n"
            f"STAGE 1 — Individual Responses:\n{stage1_text}\n\n"
            f"STAGE 2 — Peer Rankings:\n{stage2_text}\n\n"
            "Synthesize this into a single, comprehensive, accurate final "
            "answer. Be decisive. Where the council disagrees, take a "
            "position and explain why."
        )
    else:
        chairman_prompt = f"""You are the Chairman of an LLM Council with 6 members organized into two teams.

STRATEGISTS — high-level reviewers. Architect, Critical Reviewer, Stress Tester.
BUILDERS — implementation realists. Each thinks like a coding agent reading a spec for the first time and asks "what would block me from building this?"

Stage 2 was cross-team peer review: each strategist ranked the builders' responses, each builder ranked the strategists'. Neither team reviewed its own work — this surfaces blind spots, not popularity contests.

Mode: {mode_label}
Original Question: {user_query}

═══════════════════════════════════════
STRATEGIST RESPONSES
═══════════════════════════════════════
{_fmt_responses(strategists)}

═══════════════════════════════════════
BUILDER RESPONSES
═══════════════════════════════════════
{_fmt_responses(builders)}

═══════════════════════════════════════
STRATEGISTS' CROSS-REVIEW OF BUILDERS
═══════════════════════════════════════
{_fmt_rankings(strats_reviewing_builders)}

═══════════════════════════════════════
BUILDERS' CROSS-REVIEW OF STRATEGISTS
═══════════════════════════════════════
{_fmt_rankings(builders_reviewing_strats)}

═══════════════════════════════════════
YOUR TASK
═══════════════════════════════════════
Synthesize this into a decisive answer. Structure your response in two parts.

**Part 1 — Where the teams converge and diverge:**
- HIGH CONFIDENCE (both teams flagged it): list each point and which members raised it.
- DISAGREEMENT (one team flags it, the other dismisses or contradicts): list each conflict and take a position.
- SINGLE-TEAM OBSERVATIONS (only one team raised it): list each, and note whether the other team likely missed it because it's outside their lens.

**Part 2 — Your verdict:**
The decisive answer to the user's question. Be specific. Don't hedge. Where the teams disagreed, explain why you ruled the way you did."""

    messages = _system_message() + [{"role": "user", "content": chairman_prompt}]
    response = await query_model(CHAIRMAN_MODEL, messages)
    if response is None:
        return {"model": CHAIRMAN_MODEL, "response": "Error: Unable to generate final synthesis."}
    return {"model": CHAIRMAN_MODEL, "response": response.get("content", "")}


async def stage3_synthesize_debate(
    user_query: str,
    round1: List[Dict[str, Any]],
    round2: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Stage 3 (debate): Chairman synthesizes the two debate rounds.

    With 6 models and tier-balanced stances, each stance is held by one
    strategist + one builder. The chairman is shown both axes (stance and
    tier) so it can detect patterns like "the builders carrying the for-side
    all surfaced practical blockers the strategists glossed over."
    """

    def _fmt_entries(items: List[Dict[str, Any]], round_label: str) -> str:
        return "\n\n".join(
            f"Model: {r['model']} (stance: {r['stance']}, tier: {r.get('tier', '?')})\n"
            f"{round_label}: {r['response']}"
            for r in items
        )

    round1_text = _fmt_entries(round1, "Round 1")
    round2_text = _fmt_entries(round2, "Round 2 rebuttal")

    chairman_prompt = f"""You are the Chairman of an LLM Council adjudicating a two-round architectural debate.

The 6 council members are split into two teams (strategists vs. builders) and were assigned stances (for / against / neutral) at random in a way that gave each stance one strategist and one builder. They argued their assigned positions, not their own views.

Original Question: {user_query}

ROUND 1 — Opening arguments:
{round1_text}

ROUND 2 — Rebuttals:
{round2_text}

Deliver a verdict. Identify:
- Which arguments survived rebuttal.
- Which collapsed under counter-pressure.
- Where the strategist + builder on the same stance diverged from each other (e.g., the strategist made a clean theoretical case while the builder surfaced a practical blocker that undermines it, or vice versa). These divergences are often the most interesting signal.
- Which trade-offs are real vs. exaggerated.

Then give a clear recommendation — not "it depends," but the decision you would make and the conditions under which you'd reconsider it."""

    messages = _system_message() + [{"role": "user", "content": chairman_prompt}]
    response = await query_model(CHAIRMAN_MODEL, messages)
    if response is None:
        return {"model": CHAIRMAN_MODEL, "response": "Error: Unable to generate final synthesis."}
    return {"model": CHAIRMAN_MODEL, "response": response.get("content", "")}


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """Parse the FINAL RANKING section from the model's response."""
    import re

    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered_matches = re.findall(r"\d+\.\s*Response [A-Z]", ranking_section)
            if numbered_matches:
                return [re.search(r"Response [A-Z]", m).group() for m in numbered_matches]
            matches = re.findall(r"Response [A-Z]", ranking_section)
            return matches

    matches = re.findall(r"Response [A-Z]", ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Average rank position across cross-team peer evaluations.

    With cross-review, each model's aggregate score reflects how its team's
    work was judged BY THE OTHER TEAM — strategists are ranked by builders,
    builders by strategists. Falls back to the "all" key if Stage 2 ran in
    full-mesh fallback mode.
    """
    from collections import defaultdict

    model_positions: Dict[str, List[int]] = defaultdict(list)

    # Which label map applies to a given reviewer? A strategist reviewer ranked
    # builders → use label_to_model["builders"]. A builder reviewer ranked
    # strategists → use label_to_model["strategists"]. Full-mesh fallback has
    # everything under "all".
    for ranking in stage2_results:
        reviewer_tier = ranking.get("reviewer_tier")
        if "all" in label_to_model:
            labels = label_to_model["all"]
        elif reviewer_tier == "strategist":
            labels = label_to_model.get("builders", {})
        elif reviewer_tier == "builder":
            labels = label_to_model.get("strategists", {})
        else:
            continue

        parsed = parse_ranking_from_text(ranking["ranking"])
        for position, label in enumerate(parsed, start=1):
            if label in labels:
                model_positions[labels[label]].append(position)

    aggregate: List[Dict[str, Any]] = []
    for model, positions in model_positions.items():
        if positions:
            aggregate.append(
                {
                    "model": model,
                    "average_rank": round(sum(positions) / len(positions), 2),
                    "rankings_count": len(positions),
                }
            )
    aggregate.sort(key=lambda x: x["average_rank"])
    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """Generate a short title for a conversation based on the first user message."""
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""
    messages = [{"role": "user", "content": title_prompt}]
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)
    if response is None:
        return "New Conversation"
    title = response.get("content", "New Conversation").strip().strip("\"'")
    if len(title) > 50:
        title = title[:47] + "..."
    return title


async def run_full_council(
    user_query: str,
    mode_key: Optional[str] = None,
) -> Tuple[List, List, Dict, Dict]:
    """Run the complete 3-stage council process, mode-aware.

    Roles & free-chat modes: stage1 = role-aware responses, stage2 = cross-
    team peer review, stage3 = chairman synthesis with tier grouping.

    Debate mode: stage1 = round 1 (tier-balanced stances), stage2 = round 2
    rebuttals (NOT a ranking), stage3 = chairman verdict.
    """
    mode_def = get_mode(mode_key)

    # --- Architecture Debate branch ---
    if mode_def and mode_def.get("flow") == "debate":
        round1, stance_map = await debate_round1(user_query, mode_def)
        if not round1:
            return [], [], {"model": "error", "response": "All models failed in round 1."}, {
                "mode": mode_key,
                "flow": "debate",
            }

        round2 = await debate_round2(user_query, mode_def, round1, stance_map)
        stage3_result = await stage3_synthesize_debate(user_query, round1, round2)
        metadata = {
            "mode": mode_key,
            "flow": "debate",
            "stance_map": stance_map,
        }
        return round1, round2, stage3_result, metadata

    # --- Roles & free-chat branch ---
    stage1_results = await stage1_collect_responses(user_query, mode_def)
    if not stage1_results:
        return [], [], {"model": "error", "response": "All models failed to respond. Please try again."}, {
            "mode": mode_key,
            "flow": (mode_def or {}).get("flow", "free"),
        }

    stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
    stage3_result = await stage3_synthesize_final(
        user_query, stage1_results, stage2_results, mode_def
    )

    metadata = {
        "mode": mode_key,
        "flow": (mode_def or {}).get("flow", "free"),
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
    }
    return stage1_results, stage2_results, stage3_result, metadata
