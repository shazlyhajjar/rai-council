"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio
import sys
import traceback

from . import storage
from .council import (
    run_full_council,
    generate_conversation_title,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
    stage3_synthesize_debate,
    calculate_aggregate_rankings,
    debate_round1,
    debate_round2,
)
from .modes import get_mode, list_modes_for_ui
from . import context as council_context
from . import verdicts as verdicts_db


def _hydrate_verdicts(conversation: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the current verdict state to every assistant message that has one.

    The `verdict` field carries id + decision + reasoning + timestamps so the
    UI can render Accept / Override / "Overridden — reasoning" without an
    extra round-trip per message.
    """
    for msg in conversation.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        vid = msg.get("verdict_id")
        if not vid:
            continue
        v = verdicts_db.get_verdict(vid)
        if not v:
            continue
        msg["verdict"] = {
            "id": v["id"],
            "decision": v.get("decision"),
            "override_reasoning": v.get("override_reasoning"),
            "decided_at": v.get("decided_at"),
            "created_at": v.get("created_at"),
        }
    return conversation


def _build_model_positions(stage1: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Distill stage 1 into the position list we persist in the verdict log."""
    positions: List[Dict[str, Any]] = []
    for r in stage1 or []:
        pos: Dict[str, Any] = {
            "model": r.get("model"),
            "response": r.get("response", ""),
        }
        if r.get("role"):
            pos["role"] = r["role"]
        if r.get("stance"):
            pos["stance"] = r["stance"]
        if r.get("tier"):
            pos["tier"] = r["tier"]
        positions.append(pos)
    return positions

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure the verdict log schema exists before any request lands.
verdicts_db.init_db()


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    mode: Optional[str] = None  # "spec_review" | "architecture_debate" | "code_review" | None
    attachment: Optional[str] = None  # Free-form text/markdown context pasted by the user


def compose_council_input(content: str, attachment: Optional[str]) -> str:
    """Merge a user message with optional attached context into one prompt.

    Kept narrow on purpose: this is the ONLY place attachment + question get
    concatenated, so council.py and the orchestration stay unchanged.
    """
    if not attachment or not attachment.strip():
        return content
    return (
        "[Attached context from the user]\n"
        "---\n"
        f"{attachment.strip()}\n"
        "---\n\n"
        "[Question]\n"
        f"{content}"
    )


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/modes")
async def get_modes():
    """List available operating modes for the chat UI dropdown."""
    return {"modes": list_modes_for_ui()}


class UpdateContextRequest(BaseModel):
    """Replace the RAI Council Brief contents."""
    content: str


@app.get("/api/context")
async def get_context_endpoint():
    """Return the RAI Council Brief plus metadata (loaded/words/path/updated_at)."""
    status = council_context.get_brief_status()
    return {**status, "content": council_context.get_brief()}


@app.put("/api/context")
async def update_context_endpoint(request: UpdateContextRequest):
    """Replace the brief on disk and invalidate the in-memory cache."""
    council_context.set_brief(request.content)
    status = council_context.get_brief_status()
    return {**status, "content": council_context.get_brief()}


class DecisionRequest(BaseModel):
    """Accept or override a verdict, with optional reasoning (only used for overrides)."""
    decision: str  # 'accept' | 'override'
    reasoning: Optional[str] = None


@app.get("/api/verdicts")
async def list_verdicts_endpoint(
    mode: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = 200,
):
    """Browse the verdict log. `decision` accepts accept|override|undecided."""
    return {"verdicts": verdicts_db.list_verdicts(mode=mode, decision=decision, limit=limit)}


@app.get("/api/verdicts/{verdict_id}")
async def get_verdict_endpoint(verdict_id: str):
    v = verdicts_db.get_verdict(verdict_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Verdict not found")
    return v


@app.post("/api/verdicts/{verdict_id}/decision")
async def decide_verdict_endpoint(verdict_id: str, request: DecisionRequest):
    if request.decision not in verdicts_db.VALID_DECISIONS:
        raise HTTPException(status_code=400, detail=f"decision must be one of {sorted(verdicts_db.VALID_DECISIONS)}")
    updated = verdicts_db.set_decision(verdict_id, request.decision, request.reasoning)
    if updated is None:
        raise HTTPException(status_code=404, detail="Verdict not found")
    return updated


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages and verdict state."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _hydrate_verdicts(conversation)


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message (store the raw content + attachment separately so the
    # conversation log shows what the user actually typed, not the merged prompt).
    storage.add_user_message(conversation_id, request.content, attachment=request.attachment)

    # If this is the first message, generate a title (from the question only —
    # a 5,000-word attachment would tank title quality).
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process (mode-aware). The attachment, if any,
    # is folded into the prompt before the council sees it.
    council_input = compose_council_input(request.content, request.attachment)
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        council_input,
        mode_key=request.mode,
    )

    # Log the verdict (only if we actually got a chairman synthesis).
    verdict_id: Optional[str] = None
    if stage3_result and stage3_result.get("response") and stage3_result.get("model") != "error":
        verdict_id = verdicts_db.create_verdict(
            conversation_id=conversation_id,
            mode=request.mode,
            flow=metadata.get("flow") if metadata else None,
            question=request.content,
            model_positions=_build_model_positions(stage1_results),
            chairman_model=stage3_result["model"],
            chairman_verdict=stage3_result["response"],
        )

    # Add assistant message with all stages + mode metadata + verdict id
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result,
        metadata=metadata,
        verdict_id=verdict_id,
    )

    # Return the complete response with metadata + verdict id
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata,
        "verdict_id": verdict_id,
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    mode_key = request.mode
    mode_def = get_mode(mode_key)
    flow = (mode_def or {}).get("flow", "free")
    council_input = compose_council_input(request.content, request.attachment)

    async def event_generator():
        try:
            # Store the user's raw input + attachment (NOT the merged prompt) so the
            # conversation log shows what was typed.
            storage.add_user_message(
                conversation_id,
                request.content,
                mode=mode_key,
                attachment=request.attachment,
            )

            # Announce the mode + flow up front so the UI can swap stage labels.
            yield f"data: {json.dumps({'type': 'mode_start', 'mode': mode_key, 'flow': flow})}\n\n"

            # Title comes from the question only — never the attachment.
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            if flow == "debate":
                yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
                round1, stance_map = await debate_round1(council_input, mode_def)
                yield f"data: {json.dumps({'type': 'stage1_complete', 'data': round1, 'metadata': {'stance_map': stance_map}})}\n\n"

                yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
                round2 = await debate_round2(council_input, mode_def, round1, stance_map)
                yield f"data: {json.dumps({'type': 'stage2_complete', 'data': round2, 'metadata': {'stance_map': stance_map}})}\n\n"

                yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
                stage3_result = await stage3_synthesize_debate(council_input, round1, round2)
                yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

                stage1_results, stage2_results = round1, round2
                final_metadata = {"mode": mode_key, "flow": flow, "stance_map": stance_map}
            else:
                yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
                stage1_results = await stage1_collect_responses(council_input, mode_def)
                yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

                yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
                stage2_results, label_to_model = await stage2_collect_rankings(council_input, stage1_results)
                aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
                yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

                yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
                stage3_result = await stage3_synthesize_final(council_input, stage1_results, stage2_results, mode_def)
                yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

                final_metadata = {
                    "mode": mode_key,
                    "flow": flow,
                    "label_to_model": label_to_model,
                    "aggregate_rankings": aggregate_rankings,
                }

            # Log the verdict (if the Chairman returned a real synthesis).
            verdict_id: Optional[str] = None
            if (
                stage3_result
                and stage3_result.get("response")
                and stage3_result.get("model") != "error"
            ):
                verdict_id = verdicts_db.create_verdict(
                    conversation_id=conversation_id,
                    mode=mode_key,
                    flow=flow,
                    question=request.content,
                    model_positions=_build_model_positions(stage1_results),
                    chairman_model=stage3_result["model"],
                    chairman_verdict=stage3_result["response"],
                )
                yield f"data: {json.dumps({'type': 'verdict_created', 'verdict_id': verdict_id})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message with mode metadata + verdict id
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                metadata=final_metadata,
                verdict_id=verdict_id,
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except asyncio.CancelledError:
            # The client disconnected (browser navigated away / refreshed mid-
            # stream). Log it so the next time we see "user msg saved but no
            # assistant msg" we know whether it was a client disconnect vs an
            # actual server-side bug. Re-raise so the runtime can finish
            # cancelling the task cleanly.
            print(
                f"[stream] client disconnected mid-stream for conv "
                f"{conversation_id} (mode={mode_key})",
                file=sys.stderr,
                flush=True,
            )
            raise
        except Exception as e:
            # Full traceback to stderr — the SSE catch-all used to swallow
            # everything silently, leaving no fingerprint. Now any future
            # failure shows up in the backend log.
            tb = traceback.format_exc()
            print(
                f"[stream] error during conv {conversation_id} "
                f"(mode={mode_key}):\n{tb}",
                file=sys.stderr,
                flush=True,
            )
            try:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            except Exception:
                # If even the error yield fails (e.g. client already gone),
                # don't compound the failure.
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
