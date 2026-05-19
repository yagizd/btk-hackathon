from fastapi import APIRouter, HTTPException
from database import get_db
from services import gemini_service

router = APIRouter(prefix="/api/returns", tags=["returns"])


def _row_with_classification(row) -> dict:
    return {
        "order_id": row["id"],
        "marketplace": row["marketplace"],
        "marketplace_order_id": row["marketplace_order_id"],
        "customer_name": row["customer_name"],
        "customer_city": row["customer_city"],
        "gross_amount": row["gross_amount"],
        "order_date": row["order_date"],
        "product_name": row["product_name"],
        "category": row["category"],
        "reason": row["reason"],
        "refund_category": row["refund_category"],
        "kdv_adjustment_needed": bool(row["kdv_adjustment_needed"]) if row["kdv_adjustment_needed"] is not None else None,
        "gemini_explanation": row["gemini_explanation"],
        "gemini_confidence": row["gemini_confidence"],
        "classified_at": row["classified_at"],
    }


@router.get("/")
def list_returns():
    """is_return=1 olan tüm siparişleri sınıflandırma bilgisiyle birlikte döner."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT
                 o.id, o.marketplace, o.marketplace_order_id, o.customer_name,
                 o.customer_city, o.gross_amount, o.order_date,
                 (SELECT product_name FROM order_lines WHERE order_id=o.id LIMIT 1) AS product_name,
                 (SELECT category FROM order_lines WHERE order_id=o.id LIMIT 1) AS category,
                 rc.reason, rc.refund_category, rc.kdv_adjustment_needed,
                 rc.gemini_explanation, rc.gemini_confidence,
                 rc.created_at AS classified_at
               FROM orders o
               LEFT JOIN return_classifications rc ON rc.order_id = o.id
               WHERE o.is_return = 1
               ORDER BY o.order_date DESC"""
        ).fetchall()
    return [_row_with_classification(r) for r in rows]


@router.post("/{order_id}/classify")
def classify_return(order_id: int):
    with get_db() as conn:
        order = conn.execute(
            "SELECT id, is_return FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if not order or not order["is_return"]:
            raise HTTPException(status_code=404, detail="İade siparişi bulunamadı")

        line = conn.execute(
            "SELECT product_name FROM order_lines WHERE order_id=? LIMIT 1",
            (order_id,),
        ).fetchone()
        product_name = line["product_name"] if line else ""

    result = gemini_service.classify_return_reason(product_name, customer_notes="")

    with get_db() as conn:
        conn.execute(
            """INSERT INTO return_classifications
                 (order_id, reason, refund_category, kdv_adjustment_needed,
                  gemini_explanation, gemini_confidence)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(order_id) DO UPDATE SET
                 reason=excluded.reason,
                 refund_category=excluded.refund_category,
                 kdv_adjustment_needed=excluded.kdv_adjustment_needed,
                 gemini_explanation=excluded.gemini_explanation,
                 gemini_confidence=excluded.gemini_confidence,
                 created_at=datetime('now')""",
            (
                order_id,
                result["reason"],
                result["refund_category"],
                1 if result["kdv_adjustment_needed"] else 0,
                result["explanation"],
                result["confidence"],
            ),
        )

    return {"order_id": order_id, **result}


@router.post("/classify-all")
def classify_all_returns():
    """Henüz sınıflandırılmamış iadeleri Gemini ile işler."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT o.id FROM orders o
               LEFT JOIN return_classifications rc ON rc.order_id = o.id
               WHERE o.is_return = 1 AND rc.order_id IS NULL"""
        ).fetchall()
        pending_ids = [r["id"] for r in rows]

    classified = 0
    for oid in pending_ids:
        try:
            classify_return(oid)
            classified += 1
        except Exception as e:
            print(f"[returns/classify-all] {oid} atlandı: {str(e).encode('ascii', 'replace').decode()}")

    return {"classified": classified, "total": len(pending_ids)}
