"""
Agent tools — Gemini'nin function calling ile çağırabileceği saf DB sorguları.
Her tool: küçük input, küçük JSON output, yan etki yok.
"""
from typing import Optional
from database import get_db


# ── Tool implementations ────────────────────────────────────────────────────

def tool_get_metrics(marketplace: Optional[str] = None, include_returns: bool = False) -> dict:
    """Genel satış metrikleri. Marketplace verilirse onunla filtrele."""
    where = ["1=1"]
    params: list = []
    if marketplace:
        where.append("marketplace = ?")
        params.append(marketplace)
    where_sql = " AND ".join(where)

    with get_db() as conn:
        rows = conn.execute(
            f"SELECT marketplace, is_return, gross_amount, commission, net_payout "
            f"FROM orders WHERE {where_sql}",
            params,
        ).fetchall()
    rows = [dict(r) for r in rows]
    normal = [r for r in rows if not r["is_return"]]
    returns = [r for r in rows if r["is_return"]]
    return {
        "marketplace": marketplace or "all",
        "order_count": len(normal),
        "return_count": len(returns),
        "total_gross": round(sum(r["gross_amount"] for r in normal), 2),
        "total_commission": round(sum(r["commission"] for r in normal), 2),
        "total_net": round(sum(r["net_payout"] for r in (rows if include_returns else normal)), 2),
        "marketplaces": sorted({r["marketplace"] for r in rows}),
    }


def tool_list_orders(
    marketplace: Optional[str] = None,
    classify_status: Optional[str] = None,
    is_return: Optional[bool] = None,
    customer_substring: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """Filtrelenmiş sipariş listesi. Tek kalem özet halinde döner."""
    where = ["1=1"]
    params: list = []
    if marketplace:
        where.append("marketplace = ?"); params.append(marketplace)
    if classify_status:
        where.append("classify_status = ?"); params.append(classify_status)
    if is_return is not None:
        where.append("is_return = ?"); params.append(1 if is_return else 0)
    if customer_substring:
        where.append("LOWER(customer_name) LIKE LOWER(?)"); params.append(f"%{customer_substring}%")
    limit = max(1, min(int(limit or 10), 50))
    sql = (
        f"SELECT id, marketplace, marketplace_order_id, customer_name, customer_city, "
        f"gross_amount, net_payout, commission, classify_status, is_return, order_date "
        f"FROM orders WHERE {' AND '.join(where)} "
        f"ORDER BY order_date DESC LIMIT ?"
    )
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"count": len(rows), "orders": [dict(r) for r in rows]}


def tool_get_top_products(n: int = 5) -> dict:
    """En çok ciro üreten ürünler (iade hariç)."""
    n = max(1, min(int(n or 5), 20))
    with get_db() as conn:
        rows = conn.execute(
            """SELECT product_name, SUM(quantity) AS qty,
                      SUM(quantity * unit_price) AS revenue,
                      COUNT(DISTINCT order_id) AS order_count
               FROM order_lines ol
               JOIN orders o ON o.id = ol.order_id
               WHERE o.is_return = 0
               GROUP BY product_name
               ORDER BY revenue DESC LIMIT ?""",
            (n,),
        ).fetchall()
    return {"top_products": [dict(r) for r in rows]}


def tool_check_reconciliation(marketplace: str = "Trendyol") -> dict:
    """Mevcut payout mutabakat özeti (tek pazaryeri için)."""
    # Reuse the route logic without HTTP
    from routers.reconciliation import get_reconciliation  # late import to avoid cycle
    try:
        data = get_reconciliation()  # type: ignore
        return {
            "marketplace": data.get("marketplace"),
            "expected_amount": data.get("expected_amount"),
            "actual_amount": data.get("actual_amount"),
            "difference": data.get("difference"),
            "severity": data.get("severity"),
            "root_cause": data.get("root_cause"),
            "out_of_band_count": (data.get("commission_check") or {}).get("out_of_band_count"),
            "payout_lines": data.get("payout_lines"),
        }
    except Exception as e:
        return {"error": f"Reconciliation hesaplanamadı: {str(e)[:120]}"}


def tool_find_uncertain_classifications(threshold: float = 0.75) -> dict:
    """gemini_confidence < threshold olan satırlar (manuel inceleme gereği)."""
    threshold = float(threshold or 0.75)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT l.id AS line_id, l.order_id, l.product_name, l.category,
                      l.gemini_kdv_rate, l.gemini_confidence, l.gemini_reasoning,
                      o.marketplace, o.marketplace_order_id
               FROM order_lines l
               JOIN orders o ON o.id = l.order_id
               WHERE l.gemini_confidence IS NOT NULL
                 AND l.gemini_confidence < ?
                 AND (l.user_approved IS NULL OR l.user_approved = 0)
               ORDER BY l.gemini_confidence ASC""",
            (threshold,),
        ).fetchall()
    return {"count": len(rows), "threshold": threshold, "lines": [dict(r) for r in rows]}


def tool_get_invoice_by_number(invoice_number: str) -> dict:
    """Fatura numarasına göre fatura detayı."""
    if not invoice_number:
        return {"error": "invoice_number boş"}
    with get_db() as conn:
        row = conn.execute(
            """SELECT i.*, o.marketplace, o.marketplace_order_id, o.customer_name, o.gross_amount
               FROM invoices i JOIN orders o ON o.id = i.order_id
               WHERE i.invoice_number = ?""",
            (invoice_number,),
        ).fetchone()
    if not row:
        return {"error": f"{invoice_number} bulunamadı"}
    d = dict(row)
    d.pop("ubl_xml", None)  # XML payload prompt'a girmesin
    return {"invoice": d}


def tool_compute_kdv_breakdown() -> dict:
    """Onaylanmış satırlardan KDV oranı bazında brüt + KDV tutar dağılımı."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT l.gemini_kdv_rate AS kdv,
                      SUM(l.quantity * l.unit_price) AS net_base,
                      SUM(l.quantity * l.unit_price * l.gemini_kdv_rate / 100.0) AS kdv_tutar,
                      COUNT(*) AS line_count
               FROM order_lines l
               JOIN orders o ON o.id = l.order_id
               WHERE o.is_return = 0 AND l.gemini_kdv_rate IS NOT NULL
               GROUP BY l.gemini_kdv_rate
               ORDER BY l.gemini_kdv_rate ASC"""
        ).fetchall()
    breakdown = [
        {
            "kdv_orani": int(r["kdv"]),
            "net_matrah": round(r["net_base"] or 0, 2),
            "kdv_tutar": round(r["kdv_tutar"] or 0, 2),
            "satir_sayisi": r["line_count"],
        }
        for r in rows
    ]
    return {
        "breakdown": breakdown,
        "toplam_kdv": round(sum(b["kdv_tutar"] for b in breakdown), 2),
        "toplam_matrah": round(sum(b["net_matrah"] for b in breakdown), 2),
    }


def tool_get_returns_summary() -> dict:
    """İade siparişlerinin özeti + neden dağılımı."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT o.id, o.marketplace_order_id, o.customer_name, o.gross_amount,
                      rc.reason, rc.refund_category, rc.kdv_adjustment_needed
               FROM orders o
               LEFT JOIN return_classifications rc ON rc.order_id = o.id
               WHERE o.is_return = 1
               ORDER BY o.order_date DESC"""
        ).fetchall()
    rows = [dict(r) for r in rows]
    by_reason: dict[str, int] = {}
    for r in rows:
        reason = r.get("reason") or "unclassified"
        by_reason[reason] = by_reason.get(reason, 0) + 1
    return {
        "count": len(rows),
        "by_reason": by_reason,
        "returns": rows,
    }


# ── Registry + Gemini function declarations ─────────────────────────────────

TOOL_REGISTRY = {
    "get_metrics": tool_get_metrics,
    "list_orders": tool_list_orders,
    "get_top_products": tool_get_top_products,
    "check_reconciliation": tool_check_reconciliation,
    "find_uncertain_classifications": tool_find_uncertain_classifications,
    "get_invoice_by_number": tool_get_invoice_by_number,
    "compute_kdv_breakdown": tool_compute_kdv_breakdown,
    "get_returns_summary": tool_get_returns_summary,
}


# Gemini FunctionDeclaration JSON şemaları. Schema.type değerleri UPPERCASE olmalı.
TOOL_DECLARATIONS = [
    {
        "name": "get_metrics",
        "description": "Satış metriklerini döner: brüt satış, komisyon, net hak ediş, sipariş sayısı, iade sayısı. Tüm pazaryerleri için (varsayılan) veya belirli bir pazaryeri için.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "marketplace": {"type": "STRING", "description": "Filtrelenecek pazaryeri (örn: 'Trendyol', 'Hepsiburada'). Boş bırakılırsa tümü."},
                "include_returns": {"type": "BOOLEAN", "description": "Net hesaplamaya iadeleri dahil et."},
            },
        },
    },
    {
        "name": "list_orders",
        "description": "Filtrelenebilir sipariş listesi döner. Filtre vermezsen son N siparişi getirir. Tek bir müşterinin siparişlerini görmek için customer_substring kullan.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "marketplace": {"type": "STRING"},
                "classify_status": {"type": "STRING", "description": "pending | classified | approved | rejected"},
                "is_return": {"type": "BOOLEAN"},
                "customer_substring": {"type": "STRING", "description": "Müşteri adında geçen alt dize (case-insensitive)"},
                "limit": {"type": "INTEGER", "description": "Maks 50, varsayılan 10"},
            },
        },
    },
    {
        "name": "get_top_products",
        "description": "Ciro açısından en çok satan ürünleri döner (iade hariç).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "n": {"type": "INTEGER", "description": "Kaç ürün, 1-20 arası, varsayılan 5"},
            },
        },
    },
    {
        "name": "check_reconciliation",
        "description": "Pazaryeri payout mutabakatının mevcut durumunu döner: beklenen vs gerçekleşen, fark, risk seviyesi, kök neden, bant dışı komisyon sayısı.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "marketplace": {"type": "STRING", "description": "Varsayılan: Trendyol"},
            },
        },
    },
    {
        "name": "find_uncertain_classifications",
        "description": "Gemini KDV güven skoru threshold altında olan ve henüz onaylanmamış sipariş satırlarını döner. Manuel inceleme gereken kalemler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "threshold": {"type": "NUMBER", "description": "0-1 arası, varsayılan 0.75"},
            },
        },
    },
    {
        "name": "get_invoice_by_number",
        "description": "Fatura numarasına göre fatura detaylarını döner (sipariş, müşteri, tutar, tür, statü).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "invoice_number": {"type": "STRING"},
            },
            "required": ["invoice_number"],
        },
    },
    {
        "name": "compute_kdv_breakdown",
        "description": "Onaylanmış satırlardan KDV oranı bazında brüt matrah ve KDV tutar dağılımını döner. Beyan hazırlığı için.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "get_returns_summary",
        "description": "Tüm iade siparişlerinin özeti + Gemini'nin sınıflandırdığı neden dağılımı.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
]


def execute_tool(name: str, args: dict) -> dict:
    """Tool registry'den bir aracı güvenli şekilde çağır."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"argüman hatası: {str(e)[:200]}"}
    except Exception as e:
        return {"error": f"çalışma hatası: {str(e)[:200]}"}
