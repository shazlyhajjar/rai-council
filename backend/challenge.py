"""Stage-aware self-challenge passes (Path A, "Challenge Mode").

After every model output at every stage, when challenge mode is on, we feed
the model its own response back with a challenge prompt that pushes it past
the surface-level first-pass behaviour. The same model then produces a
revised, complete response — not a supplement — which is the version that
moves on to the next stage.

Three stages, three prompts. The chairman prompt is intentionally different:
it focuses on synthesis-specific failure modes (dropped findings, smoothed-
over disagreements, lens over-weighting) rather than generic "look harder."

If a challenge call fails or returns nothing usable, the caller falls back
to the original response so a flaky API call can't take down a whole stage.
"""

from typing import Any, Dict, List, Optional

from .openrouter import query_model


# ─── Stage 1: each model's initial response ────────────────────────────────
STAGE1_CHALLENGE_PROMPT = """You just produced the analysis above. Assume you missed 30-40% of the real issues in your first pass — first responses are reliably surface-level.

Re-verify every claim against the original input. Specifically hunt for:
- Cross-references that contradict each other (something is described one way in one place, another way elsewhere)
- Edge cases you glossed over with "this should handle…" without spelling out how
- Assumptions you accepted as given rather than checking against the source material
- Anything you marked "fine" or "looks good" or skipped silently because nothing obvious was wrong

Produce a REVISED COMPLETE analysis under your same role/lens — not a supplement, not a "things I'd add" list. Rewrite from scratch with the deeper pass folded in. If your original analysis was largely correct, your revision can echo it; but you must re-derive it, not copy it."""


# ─── Stage 2: each cross-review ranking ────────────────────────────────────
STAGE2_CHALLENGE_PROMPT = """You just produced the cross-team review and ranking above. Assume you missed 30-40% of the real signal in the responses you reviewed.

Re-verify every judgment you made:
- Did you praise something because it sounded confident or because it was actually substantiated against the original question?
- Did you under-weight a response because its surface style was less polished, even though its substance was sharper?
- Did you compare responses on the most important axes — concrete findings, evidence, and consequence — or on incidental features (length, formatting, tone)?
- Are there findings in the responses you ranked that you ignored because they didn't fit your initial mental model of "what a good answer looks like here"?

Produce a REVISED COMPLETE review with a fresh FINAL RANKING — not a supplement. Use the same strict format requirements (a "FINAL RANKING:" header followed by a numbered list of "1. Response X" entries, nothing after). The ranking may stay the same or change; what matters is that it's been re-derived, not copied."""


# ─── Stage 3: chairman synthesis ───────────────────────────────────────────
STAGE3_CHALLENGE_PROMPT = """You just synthesized the council's responses + cross-reviews into the verdict above. The single biggest failure mode of a synthesis step is dropping or smoothing over findings without admitting it. Assume your verdict silently dropped or smoothed 30-40% of the real signal.

Check specifically:
1. **Inventory check.** Walk every concrete observation each of the 6 members raised (strategists + builders). For each, can you point to where it appears in your verdict? If not, why was it dropped?
2. **Disagreement check.** Where the council disagreed (a strategist flagged something a builder dismissed, or vice versa), did you take an explicit position with a reason, or did you smooth the disagreement away by softening both sides?
3. **Lens check.** Did the strategist lens or the builder lens disproportionately shape your verdict? If yes, why — and is that defensible given the question?
4. **Comfort check.** Did you drop or downplay findings that were uncomfortable, hard to reconcile, or that would force the user to do significant rework?

Produce a REVISED COMPLETE verdict that:
- Names explicitly the findings you originally dropped or smoothed (a brief paragraph at the top — "On reflection, my first pass omitted X, Y, Z; I'm folding them back in.")
- Then delivers the full Part 1 (HIGH CONFIDENCE / DISAGREEMENT / SINGLE-TEAM OBSERVATIONS) and Part 2 (verdict) sections, decisive and specific, honestly weighing all 6 perspectives.

If your original verdict was already complete and balanced, your revision can echo it — but you must re-derive it through the four checks above, not copy it."""


_STAGE_PROMPTS = {
    "stage1": STAGE1_CHALLENGE_PROMPT,
    "stage2": STAGE2_CHALLENGE_PROMPT,
    "stage3": STAGE3_CHALLENGE_PROMPT,
}


async def challenge_response(
    *,
    model: str,
    original_messages: List[Dict[str, str]],
    initial_response: str,
    stage: str,
) -> Optional[str]:
    """Run a self-challenge pass for a single model.

    `original_messages` is the exact messages list used for the initial call
    (system + user). We append the model's initial response as assistant and
    a stage-specific challenge as user. Returns the revised content string,
    or None if the call failed or returned empty content (caller falls back).
    """
    challenge_prompt = _STAGE_PROMPTS.get(stage)
    if challenge_prompt is None:
        raise ValueError(f"unknown stage for challenge: {stage!r}")

    if not initial_response or not initial_response.strip():
        # Nothing to challenge — let the caller keep whatever was there.
        return None

    messages = list(original_messages) + [
        {"role": "assistant", "content": initial_response},
        {"role": "user", "content": challenge_prompt},
    ]

    response = await query_model(model, messages)
    if response is None:
        return None
    content = response.get("content", "") or ""
    return content if content.strip() else None
