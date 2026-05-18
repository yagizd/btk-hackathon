from fastapi import APIRouter
from database import get_db
from models import NLQueryRequest, NLQueryResponse
from services import gemini_service

router = APIRouter(prefix="/api", tags=["nl-query"])


@router.post("/nl-query", response_model=NLQueryResponse)
def nl_query(body: NLQueryRequest):
    with get_db() as conn:
        orders = conn.execute("SELECT * FROM orders").fetchall()
        orders_list = [dict(o) for o in orders]

    # Özet metrikler
    total_gross = sum(o["gross_amount"] for o in orders_list if not o["is_return"])
    total_commission = sum(o["commission"] for o in orders_list if not o["is_return"])
    total_net = sum(o["net_payout"] for o in orders_list)
    return_count = sum(1 for o in orders_list if o["is_return"])
    order_count = sum(1 for o in orders_list if not o["is_return"])
    marketplaces = list(set(o["marketplace"] for o in orders_list))

    # En çok satan ürünler (order_lines tablosundan)
    with get_db() as conn:
        top = conn.execute(
            """SELECT product_name, SUM(quantity) as total_qty, SUM(quantity * unit_price) as total_revenue
               FROM order_lines ol
               JOIN orders o ON o.id = ol.order_id
               WHERE o.is_return = 0
               GROUP BY product_name
               ORDER BY total_revenue DESC
               LIMIT 5"""
        ).fetchall()

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

    context = {
        "total_gross": total_gross,
        "total_commission": total_commission,
        "total_net": total_net,
        "return_count": return_count,
        "order_count": order_count,
        "marketplaces": marketplaces,
        "top_products": top_products,
        "orders_summary": orders_summary,
    }

    answer = gemini_service.answer_nl_query(body.question, context)
    return NLQueryResponse(answer=answer)
