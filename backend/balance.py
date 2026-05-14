"""Account balance / spend fetchers for the header pills.

Two providers — OpenRouter (full balance + usage) and OpenAI (month-to-date
spend via the admin /v1/organization/costs endpoint; no balance endpoint
exists on OpenAI's side, so the "remaining" calculation needs a configured
monthly cap).

All calls are cached for 60 seconds to keep the header responsive without
hammering the providers on every page mount or refocus.
"""

from __future__ import annotations

import asyncio
import calendar
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from .config import (
    OPENROUTER_API_KEY,
    OPENAI_ADMIN_API_KEY,
    OPENAI_MONTHLY_CAP,
)


_CACHE_TTL_SECONDS = 60.0
_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_locks: Dict[str, asyncio.Lock] = {
    "openrouter": asyncio.Lock(),
    "openai": asyncio.Lock(),
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _month_start_unix() -> int:
    """First-of-this-month at 00:00 UTC as a Unix timestamp."""
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return int(start.timestamp())


def _month_end_unix() -> int:
    """Last-second-of-this-month UTC. End-of-period bound for the cost query."""
    now = datetime.now(timezone.utc)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return int(end.timestamp())


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        return None
    return value


def _cache_put(key: str, value: Dict[str, Any]) -> None:
    _cache[key] = (time.monotonic(), value)


async def fetch_openrouter_balance(force: bool = False) -> Dict[str, Any]:
    """Pull credit + usage totals from OpenRouter.

    Endpoint: GET /api/v1/credits — returns {total_credits, total_usage} in USD.
    Cached for 60s; pass `force=True` to bypass cache (used by tests).
    """
    if not force:
        cached = _cache_get("openrouter")
        if cached is not None:
            return cached

    async with _locks["openrouter"]:
        # Re-check under the lock — another coroutine may have populated it.
        if not force:
            cached = _cache_get("openrouter")
            if cached is not None:
                return cached

        if not OPENROUTER_API_KEY:
            result = {
                "provider": "openrouter",
                "error": "OPENROUTER_API_KEY not configured",
                "fetched_at": _iso_now(),
            }
            _cache_put("openrouter", result)
            return result

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/credits",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                total_credits = float(data.get("total_credits", 0))
                total_usage = float(data.get("total_usage", 0))
                result = {
                    "provider": "openrouter",
                    "total_credits": round(total_credits, 4),
                    "total_usage": round(total_usage, 4),
                    "remaining": round(total_credits - total_usage, 4),
                    "currency": "USD",
                    "fetched_at": _iso_now(),
                }
        except httpx.HTTPStatusError as e:
            body = e.response.text[:200] if e.response is not None else "(no body)"
            print(
                f"[balance.openrouter] HTTP {e.response.status_code}: {body}",
                file=sys.stderr,
                flush=True,
            )
            result = {
                "provider": "openrouter",
                "error": f"HTTP {e.response.status_code}",
                "fetched_at": _iso_now(),
            }
        except Exception as e:
            print(
                f"[balance.openrouter] unexpected: {e}\n{traceback.format_exc()}",
                file=sys.stderr,
                flush=True,
            )
            result = {
                "provider": "openrouter",
                "error": str(e) or e.__class__.__name__,
                "fetched_at": _iso_now(),
            }

        _cache_put("openrouter", result)
        return result


def _sum_openai_costs(payload: Dict[str, Any]) -> float:
    """Walk the OpenAI costs response and sum every bucket's amount.value.

    Response shape (per OpenAI docs):
      {
        "object": "page",
        "data": [
          {
            "object": "bucket",
            "start_time": ...,
            "end_time": ...,
            "results": [
              {"object": "organization.costs.result",
               "amount": {"value": <float>, "currency": "usd"},
               "line_item": <str|null>,
               "project_id": <str|null>}
            ]
          },
          ...
        ],
        "has_more": false,
        "next_page": null
      }
    """
    total = 0.0
    for bucket in payload.get("data", []):
        for result in bucket.get("results", []):
            amount = result.get("amount", {})
            try:
                total += float(amount.get("value", 0))
            except (TypeError, ValueError):
                continue
    return total


async def fetch_openai_spend(force: bool = False) -> Dict[str, Any]:
    """Sum month-to-date OpenAI spend via /v1/organization/costs.

    OpenAI does NOT expose a balance endpoint via API — only via the dashboard's
    session cookie. So we pull month-to-date cost and (if a monthly cap is
    configured) compute a "remaining" figure against that cap.
    """
    if not force:
        cached = _cache_get("openai")
        if cached is not None:
            return cached

    async with _locks["openai"]:
        if not force:
            cached = _cache_get("openai")
            if cached is not None:
                return cached

        if not OPENAI_ADMIN_API_KEY:
            result = {
                "provider": "openai",
                "error": "OPENAI_ADMIN_API_KEY not configured",
                "fetched_at": _iso_now(),
            }
            _cache_put("openai", result)
            return result

        start = _month_start_unix()
        end = _month_end_unix()

        # bucket_width=1d, limit=31 → at most one page for any calendar month.
        # OpenAI's pagination cursor is `next_page`; we follow it defensively
        # in case the response is split.
        spent = 0.0
        page_token: Optional[str] = None
        try:
            # OpenAI's costs endpoint is noticeably slower than chat — give it
            # a wider window than the OpenRouter call (which is fast).
            async with httpx.AsyncClient(timeout=45.0) as client:
                for _ in range(5):  # hard ceiling on pagination loops
                    params: Dict[str, Any] = {
                        "start_time": start,
                        "end_time": end,
                        "bucket_width": "1d",
                        "limit": 31,
                    }
                    if page_token:
                        params["page"] = page_token

                    resp = await client.get(
                        "https://api.openai.com/v1/organization/costs",
                        headers={"Authorization": f"Bearer {OPENAI_ADMIN_API_KEY}"},
                        params=params,
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                    spent += _sum_openai_costs(payload)
                    if not payload.get("has_more"):
                        break
                    page_token = payload.get("next_page")
                    if not page_token:
                        break

            spent_rounded = round(spent, 4)
            result: Dict[str, Any] = {
                "provider": "openai",
                "spent_this_month": spent_rounded,
                "monthly_cap": OPENAI_MONTHLY_CAP,
                "remaining": (
                    round(OPENAI_MONTHLY_CAP - spent_rounded, 4)
                    if OPENAI_MONTHLY_CAP is not None
                    else None
                ),
                "currency": "USD",
                "fetched_at": _iso_now(),
            }
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response is not None else "(no body)"
            print(
                f"[balance.openai] HTTP {e.response.status_code}: {body}",
                file=sys.stderr,
                flush=True,
            )
            result = {
                "provider": "openai",
                "error": f"HTTP {e.response.status_code}",
                "error_detail": body,
                "fetched_at": _iso_now(),
            }
        except Exception as e:
            print(
                f"[balance.openai] unexpected: {e}\n{traceback.format_exc()}",
                file=sys.stderr,
                flush=True,
            )
            result = {
                "provider": "openai",
                "error": str(e) or e.__class__.__name__,
                "fetched_at": _iso_now(),
            }

        _cache_put("openai", result)
        return result
