import uuid
from fastapi import APIRouter
from database import get_db
from models import NLQueryRequest, NLQueryResponse
from services import gemini_service

router = APIRouter(prefix="/api", tags=["nl-query"])

MAX_HISTORY_TURNS = 5  # tek tarafta tutulan son N tur (user + assistant ayrı sayılır)


def _build_context() -> dict:
    with get_db() as conn:
        orders = conn.execute("SELECT * FROM orders").fetchall()
        orders_list = [dict(o) for o in orders]

        top = conn.execute(
            """SELECT product_name, SUM(quantity) as total_qty,
                      SUM(quantity * unit_price) as total_revenue
               FROM order_lines ol
               JOIN orders o ON o.id = ol.order_id
               WHERE o.is_return = 0
               GROUP BY product_name
               ORDER BY total_revenue DESC
               LIMIT 5"""
        ).fetchall()

    total_gross = sum(o["gross_amount"] for o in orders_list if not o["is_return"])
    total_commission = sum(o["commission"] for o in orders_list if not o["is_return"])
    total_net = sum(o["net_payout"] for o in orders_list)
    return_count = sum(1 for o in orders_list if o["is_return"])
    order_count = sum(1 for o in orders_list if not o["is_return"])
    marketplaces = list({o["marketplace"] for o in orders_list})

    top_products = [
        {"product": r["product_name"], "quantity": r["total_qty"], "revenue": r["total_revenue"]}
        for r in top
    ]
    orders_summary = [
        {
            "id": o["marketplace_order_id"],
            "marketplace": o["marketplace"],
            "customer": o["customer_name"],
            "gross": o["gross_amount"],
            "net": o["net_payout"],
            "is_return": bool(o["is_return"]),
            "date": o["order_date"],
        }
        for o in orders_list
    ]

    return {
        "total_gross": total_gross,
        "total_commission": total_commission,
        "total_net": total_net,
        "return_count": return_count,
        "order_count": order_count,
        "marketplaces": marketplaces,
        "top_products": top_products,
        "orders_summary": orders_summary,
    }


def _load_history(session_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT role, content FROM chat_sessions
               WHERE session_id=?
               ORDER BY turn ASC""",
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

        # Eski turları kırp: son 2*MAX_HISTORY_TURNS satırı tut (user+assistant çiftleri)
        max_rows = 2 * MAX_HISTORY_TURNS
        total = conn.execute(
            "SELECT COUNT(*) FROM chat_sessions WHERE session_id=?", (session_id,)
        ).fetchone()[0]
        if total > max_rows:
            keep_from = conn.execute(
                """SELECT turn FROM chat_sessions
                   WHERE session_id=?
                   ORDER BY turn DESC LIMIT 1 OFFSET ?""",
                (session_id, max_rows - 1),
            ).fetchone()
            if keep_from:
                conn.execute(
                    "DELETE FROM chat_sessions WHERE session_id=? AND turn < ?",
                    (session_id, keep_from[0]),
                )


@router.post("/nl-query", response_model=NLQueryResponse)
def nl_query(body: NLQueryRequest):
    session_id = body.session_id or str(uuid.uuid4())
    history = _load_history(session_id) if body.session_id else []

    context = _build_context()
    answer = gemini_service.answer_nl_query(body.question, context, history=history)

    _append_turn(session_id, "user", body.question)
    _append_turn(session_id, "assistant", answer)

    return NLQueryResponse(answer=answer, session_id=session_id)


@router.get("/nl-query/{session_id}/history")
def get_history(session_id: str):
    return _load_history(session_id)


@router.delete("/nl-query/{session_id}")
def reset_session(session_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM chat_sessions WHERE session_id=?", (session_id,))
    return {"session_id": session_id, "cleared": True}
