from fastapi import APIRouter
from database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/metrics")
def get_metrics():
    with get_db() as conn:
        orders = conn.execute("SELECT * FROM orders").fetchall()
        orders_list = [dict(o) for o in orders]

        pending_classify = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE classify_status='pending'"
        ).fetchone()[0]

        pending_invoices = conn.execute(
            """SELECT COUNT(*) FROM orders o
               WHERE o.classify_status='approved'
               AND NOT EXISTS (SELECT 1 FROM invoices i WHERE i.order_id=o.id)"""
        ).fetchone()[0]

    normal = [o for o in orders_list if not o["is_return"]]
    returns = [o for o in orders_list if o["is_return"]]

    total_gross = sum(o["gross_amount"] for o in normal)
    total_commission = sum(o["commission"] for o in normal)
    total_net = sum(o["net_payout"] for o in orders_list)

    return {
        "total_gross": round(total_gross, 2),
        "total_commission": round(total_commission, 2),
        "total_net": round(total_net, 2),
        "return_count": len(returns),
        "order_count": len(normal),
        "pending_classify": pending_classify,
        "pending_invoices": pending_invoices,
    }


@router.get("/chart")
def get_chart():
    """Son 7 günün günlük brüt satış + net gelir verisi"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT
                 DATE(order_date) as day,
                 SUM(CASE WHEN is_return=0 THEN gross_amount ELSE 0 END) as gross,
                 SUM(net_payout) as net
               FROM orders
               GROUP BY DATE(order_date)
               ORDER BY day DESC
               LIMIT 7"""
        ).fetchall()

    # Kronolojik sıra
    points = [{"date": r["day"], "gross": round(r["gross"], 2), "net": round(r["net"], 2)} for r in rows]
    points.reverse()
    return points


@router.get("/recent-orders")
def get_recent_orders():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, marketplace, marketplace_order_id, customer_name,
                      gross_amount, net_payout, classify_status, is_return, order_date
               FROM orders ORDER BY order_date DESC LIMIT 5"""
        ).fetchall()
    return [dict(r) for r in rows]
