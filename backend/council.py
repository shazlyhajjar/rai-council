"""3-stage LLM Council orchestration."""

from typing import List, Dict, Any, Optional, Tuple
from .openrouter import (
    query_models_parallel,
    query_models_parallel_per_messages,
    query_model,
)
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL
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
                }
            )
        return results

    # Free chat path — original behavior, but the auto-loaded RAI brief is
    # still injected as a system message so every model sees project context.
    messages = _system_message() + [{"role": "user", "content": user_query}]
    responses = await query_models_parallel(COUNCIL_MODELS, messages)
    return [
        {"model": model, "response": response.get("content", "")}
        for model, response in responses.items()
        if response is not None
    ]


async def debate_round1(
    user_query: str,
    mode_def: Dict,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Architecture Debate round 1 — randomized stances, parallel.

    Returns (results, stance_map). `results` is shaped like stage1 so the
    frontend can reuse the same renderer; each entry carries `stance`.
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
            }
        )
    return results


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Stage 2: each model ranks the anonymized stage 1 responses."""
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    label_to_model = {
        f"Response {label}": result["model"]
        for label, result in zip(labels, stage1_results)
    }

    responses_text = "\n\n".join(
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    )

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
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

    messages = _system_message() + [{"role": "user", "content": ranking_prompt}]
    responses = await query_models_parallel(COUNCIL_MODELS, messages)

    stage2_results: List[Dict[str, Any]] = []
    for model, response in responses.items():
        if response is None:
            continue
        full_text = response.get("content", "")
        stage2_results.append(
            {
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parse_ranking_from_text(full_text),
            }
        )

    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    mode_def: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Stage 3 (roles / free-chat): Chairman synthesizes from responses + rankings."""
    stage1_text = "\n\n".join(
        f"Model: {r['model']}"
        + (f" (role: {r['role']})" if r.get("role") else "")
        + f"\nResponse: {r['response']}"
        for r in stage1_results
    )
    stage2_text = "\n\n".join(
        f"Model: {r['model']}\nRanking: {r['ranking']}" for r in stage2_results
    )

    mode_label = (mode_def or {}).get("label", "Council")
    chairman_prompt = f"""You are the Chairman of an LLM Council.

Mode: {mode_label}

The council members each provided a response to the user's question (each from a different lens or role), then anonymously ranked each other's responses.

Original Question: {user_query}

STAGE 1 — Individual Responses:
{stage1_text}

STAGE 2 — Peer Rankings:
{stage2_text}

Your task as Chairman: synthesize this into a single, comprehensive, accurate final answer. Consider:
- The specific lens each member used (their role, if any).
- Patterns of agreement and disagreement.
- What the peer rankings reveal about which arguments carried weight.

Be decisive. Where the council disagrees, take a position and explain why."""

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
    """Stage 3 (debate): Chairman synthesizes the two debate rounds."""
    round1_text = "\n\n".join(
        f"Model: {r['model']} (stance: {r['stance']})\nRound 1: {r['response']}"
        for r in round1
    )
    round2_text = "\n\n".join(
        f"Model: {r['model']} (stance: {r['stance']})\nRound 2 rebuttal: {r['response']}"
        for r in round2
    )

    chairman_prompt = f"""You are the Chairman of an LLM Council adjudicating a two-round architectural debate.

Each model was assigned a stance (for / against / neutral) at random and argued from that position. They were not arguing their own views — they were arguing the assigned position as forcefully as they could.

Original Question: {user_query}

ROUND 1 — Opening arguments:
{round1_text}

ROUND 2 — Rebuttals:
{round2_text}

Your task as Chairman: deliver a verdict. Identify which arguments survived rebuttal, which collapsed, and which trade-offs are real vs. exaggerated. Then give a clear recommendation — not "it depends," but the decision you would make and the conditions under which you'd reconsider it."""

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
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Average rank position across all peer evaluations."""
    from collections import defaultdict

    model_positions = defaultdict(list)
    for ranking in stage2_results:
        parsed = parse_ranking_from_text(ranking["ranking"])
        for position, label in enumerate(parsed, start=1):
            if label in label_to_model:
                model_positions[label_to_model[label]].append(position)

    aggregate = []
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

    Roles & free-chat modes: stage1 = role-aware responses, stage2 = peer
    ranking, stage3 = chairman synthesis.

    Debate mode: stage1 = round 1 (randomized stances), stage2 = round 2
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
