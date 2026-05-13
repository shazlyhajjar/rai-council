"""SQLite-backed Verdict Log.

Every Chairman synthesis lands in a row here. The user later marks it as
"accept" or "override" (with optional reasoning). The History page browses
this table with mode/decision filters.

Schema is intentionally narrow — no foreign keys to the conversation JSON
files because those are flat-file storage and could be moved/renamed.
We keep `conversation_id` as a soft link.
"""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "verdicts.db"

# Decision values we accept on writes. NULL means "not yet decided".
VALID_DECISIONS = {"accept", "override"}


def _utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def init_db() -> None:
    """Create the verdicts table + indices if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verdicts (
                id                    TEXT PRIMARY KEY,
                conversation_id       TEXT NOT NULL,
                created_at            TEXT NOT NULL,
                mode                  TEXT,
                flow                  TEXT,
                question              TEXT NOT NULL,
                question_full         TEXT NOT NULL,
                model_positions_json  TEXT NOT NULL,
                chairman_model        TEXT NOT NULL,
                chairman_verdict      TEXT NOT NULL,
                decision              TEXT,
                override_reasoning    TEXT,
                decided_at            TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verdicts_mode ON verdicts(mode)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verdicts_decision ON verdicts(decision)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_verdicts_created ON verdicts(created_at DESC)")
        conn.commit()


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    raw = d.pop("model_positions_json", "[]")
    try:
        d["model_positions"] = json.loads(raw)
    except json.JSONDecodeError:
        d["model_positions"] = []
    return d


def create_verdict(
    conversation_id: str,
    mode: Optional[str],
    flow: Optional[str],
    question: str,
    model_positions: List[Dict[str, Any]],
    chairman_model: str,
    chairman_verdict: str,
) -> str:
    """Insert a new verdict row and return its id.

    `question` is stored both fully and truncated to 200 chars (per spec).
    `model_positions` is a list of {model, role?, stance?, response} dicts —
    serialized as JSON in one column.
    """
    init_db()
    vid = str(uuid.uuid4())
    now = _utc_iso()
    question_short = (question or "").strip()[:200]

    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO verdicts (
                id, conversation_id, created_at, mode, flow,
                question, question_full,
                model_positions_json, chairman_model, chairman_verdict
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vid,
                conversation_id,
                now,
                mode,
                flow,
                question_short,
                question or "",
                json.dumps(model_positions, ensure_ascii=False),
                chairman_model,
                chairman_verdict or "",
            ),
        )
        conn.commit()
    return vid


def get_verdict(verdict_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM verdicts WHERE id = ?", (verdict_id,)).fetchone()
        return _row_to_dict(row) if row else None


def list_verdicts(
    mode: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """List verdicts newest-first, with optional mode + decision filters.

    `decision` accepts 'accept', 'override', or 'undecided' (which matches NULL).
    Any other value is treated as no filter.
    """
    init_db()
    clauses: List[str] = []
    params: List[Any] = []

    if mode:
        clauses.append("mode = ?")
        params.append(mode)

    if decision == "undecided":
        clauses.append("decision IS NULL")
    elif decision in VALID_DECISIONS:
        clauses.append("decision = ?")
        params.append(decision)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(int(limit))

    sql = f"""
        SELECT id, conversation_id, created_at, mode, flow,
               question, chairman_model, chairman_verdict,
               decision, override_reasoning, decided_at
        FROM verdicts
        {where}
        ORDER BY created_at DESC
        LIMIT ?
    """
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def set_decision(
    verdict_id: str,
    decision: str,
    reasoning: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Mark a verdict as accepted or overridden. Returns the updated row, or None if not found."""
    init_db()
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(VALID_DECISIONS)}; got {decision!r}")

    now = _utc_iso()
    # Reasoning only makes sense for overrides — drop it for accepts to keep the column clean.
    final_reasoning = (reasoning.strip() if reasoning else None) if decision == "override" else None

    with _conn() as conn:
        cursor = conn.execute(
            """
            UPDATE verdicts
               SET decision           = ?,
                   override_reasoning = ?,
                   decided_at         = ?
             WHERE id = ?
            """,
            (decision, final_reasoning, now, verdict_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return None

    return get_verdict(verdict_id)
