import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_db
from services import agent_service
from services.agent_service import AgentError

router = APIRouter(prefix="/api/agent", tags=["agent"])

MAX_HISTORY_TURNS = 5


class AgentChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class AgentReconciliationRequest(BaseModel):
    marketplace: str = "Trendyol"
    question: Optional[str] = None  # opsiyonel: özel analiz sorusu


# ── Session helpers (chat_sessions tablosunu yeniden kullan) ────────────────

def _load_history(session_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_sessions WHERE session_id=? ORDER BY turn ASC",
            (session_id,),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def _append_turn(session_id: str, role: str, content: str):
    with get_db() as conn:
        next_turn_row = conn.execute(
            "SELECT COALESCE(MAX(turn), -1) + 1 FROM chat_sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        next_turn = next_turn_row[0]
        conn.execute(
            "INSERT INTO chat_sessions (session_id, turn, role, content) VALUES (?,?,?,?)",
            (session_id, next_turn, role, content),
        )
        max_rows = 2 * MAX_HISTORY_TURNS
        total = conn.execute(
            "SELECT COUNT(*) FROM chat_sessions WHERE session_id=?", (session_id,)
        ).fetchone()[0]
        if total > max_rows:
            keep_from = conn.execute(
                """SELECT turn FROM chat_sessions WHERE session_id=?
                   ORDER BY turn DESC LIMIT 1 OFFSET ?""",
                (session_id, max_rows - 1),
            ).fetchone()
            if keep_from:
                conn.execute(
                    "DELETE FROM chat_sessions WHERE session_id=? AND turn < ?",
                    (session_id, keep_from[0]),
                )


# ── POST /api/agent/chat (Option A) ─────────────────────────────────────────

@router.post("/chat")
def agent_chat(body: AgentChatRequest):
    session_id = body.session_id or str(uuid.uuid4())
    history = _load_history(session_id) if body.session_id else []

    try:
        result = agent_service.run_chat_agent(body.question, history=history)
    except AgentError as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "gemini_unreachable",
                "message": str(e),
                "trace": e.trace,
                "iterations": e.iterations,
            },
        )

    answer = result["answer"]
    _append_turn(session_id, "user", body.question)
    _append_turn(session_id, "assistant", answer)

    return {
        "answer": answer,
        "session_id": session_id,
        "trace": result["trace"],
        "iterations": result["iterations"],
    }


# ── POST /api/agent/reconciliation (Option B) ───────────────────────────────

@router.post("/reconciliation")
def agent_reconciliation(body: AgentReconciliationRequest):
    question = body.question or (
        f"{body.marketplace} pazaryeri için son dönem payout mutabakatını "
        f"detaylı analiz et. Komisyon, iade, kampanya ve stopaj kalemlerini incele."
    )
    try:
        result = agent_service.run_analyst_agent(question)
    except AgentError as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "gemini_unreachable",
                "message": str(e),
                "trace": e.trace,
                "iterations": e.iterations,
            },
        )

    return {
        "marketplace": body.marketplace,
        "summary": result["answer"],
        "trace": result["trace"],
        "iterations": result["iterations"],
    }
