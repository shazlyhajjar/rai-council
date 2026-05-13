"""OpenRouter API client for making LLM requests."""

import sys
import traceback
import httpx
from typing import List, Dict, Any, Optional
from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            message = data['choices'][0]['message']

            return {
                # Coerce None -> '' so downstream string ops (parse_ranking_from_text,
                # de-anonymizer, markdown render) always get a string.
                'content': message.get('content') or '',
                'reasoning_details': message.get('reasoning_details')
            }

    except httpx.HTTPStatusError as e:
        # Provider returned 4xx/5xx — log the body so we can see what OpenRouter
        # actually said (rate limit, model unavailable, invalid params, etc.).
        body_preview = e.response.text[:500] if e.response is not None else "(no body)"
        print(
            f"[openrouter] {model} → HTTP {e.response.status_code}: {body_preview}",
            file=sys.stderr,
            flush=True,
        )
        return None
    except Exception as e:
        # Anything else (timeout, connection error, JSON parse, KeyError on the
        # response shape, …). Print the traceback so silent fall-through stops
        # being silent.
        tb = traceback.format_exc()
        print(
            f"[openrouter] {model} → unexpected error: {e}\n{tb}",
            file=sys.stderr,
            flush=True,
        )
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel with the SAME message list.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # Create tasks for all models
    tasks = [query_model(model, messages) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}


async def query_models_parallel_per_messages(
    model_to_messages: Dict[str, List[Dict[str, str]]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel, each with its OWN message list.

    Used when each model needs a different system prompt, role, or stance
    (Spec Review, Code Review, Architecture Debate). Order of the returned
    dict matches insertion order of `model_to_messages`.
    """
    import asyncio

    models = list(model_to_messages.keys())
    tasks = [query_model(model, model_to_messages[model]) for model in models]

    responses = await asyncio.gather(*tasks)
    return {model: response for model, response in zip(models, responses)}
