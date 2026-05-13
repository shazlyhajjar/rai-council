"""RAI Council Brief — auto-loaded system context for every council query.

The brief lives on disk at `<project root>/RAI_Council_Brief.md`. It is read
once on first access and cached in memory; `set_brief()` writes to disk and
invalidates the cache so subsequent reads pick up the new content.

If the file is missing or empty, the council still works — the brief just
isn't prepended to system prompts and the UI shows "not loaded".
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


# Resolve relative to the project root (the parent of the `backend/` package).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRIEF_PATH = _PROJECT_ROOT / "RAI_Council_Brief.md"


# Module-level cache. None = not yet read; "" = read and empty/missing.
_cached_brief: Optional[str] = None


def _read_from_disk() -> str:
    """Return the brief contents (or '' if missing)."""
    try:
        with open(BRIEF_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except OSError as e:
        # Don't crash the server if the file becomes unreadable mid-flight.
        print(f"[context] Failed to read {BRIEF_PATH}: {e}")
        return ""


def get_brief() -> str:
    """Return the brief, reading from disk on first access."""
    global _cached_brief
    if _cached_brief is None:
        _cached_brief = _read_from_disk()
    return _cached_brief


def set_brief(content: str) -> None:
    """Replace the brief on disk and invalidate the in-memory cache.

    Empty / whitespace-only content is allowed — it effectively unloads the
    brief but leaves the file in place so the path is still discoverable.
    """
    global _cached_brief
    BRIEF_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BRIEF_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    _cached_brief = None  # next get_brief() re-reads from disk


def invalidate_cache() -> None:
    """Force the next get_brief() to re-read from disk. For tests / hot-reload."""
    global _cached_brief
    _cached_brief = None


def get_brief_status() -> Dict[str, object]:
    """Return metadata about the loaded brief, for the UI indicator."""
    content = get_brief()
    has = bool(content.strip())

    status: Dict[str, object] = {
        "loaded": has,
        "path": str(BRIEF_PATH),
    }

    if has:
        stripped = content.strip()
        status["chars"] = len(stripped)
        status["words"] = len(stripped.split())
        status["lines"] = stripped.count("\n") + 1
    else:
        status["chars"] = 0
        status["words"] = 0
        status["lines"] = 0

    try:
        mtime = BRIEF_PATH.stat().st_mtime
        status["updated_at"] = datetime.utcfromtimestamp(mtime).isoformat() + "Z"
    except OSError:
        status["updated_at"] = None

    return status
