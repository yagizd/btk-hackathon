import json
import os
import random
import string
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db
from models import OrderOut, OrderLineOut, ApproveRequest
from services import gemini_service


def _generate_invoice_number() -> str:
    """ARŞ-{yıl}-{4 haneli random} formatında fatura numarası üretir."""
    year = datetime.now().year
    suffix = "".join(random.choices(string.digits, k=4))
    return f"ARŞ-{year}-{suffix}"

router = APIRouter(prefix="/api/orders", tags=["orders"])

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixture_data")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row_to_order(row) -> dict:
    return dict(row)


def _get_order_with_lines(conn, order_id: int) -> dict:
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        return None
    lines = conn.execute("SELECT * FROM order_lines WHERE order_id=?", (order_id,)).fetchall()
    result = dict(order)
    result["lines"] = [dict(l) for l in lines]
    return result


# ── Import fixture data ───────────────────────────────────────────────────────

def import_fixtures_if_empty():
    """Uygulama başlarken fixture verilerini yükler (sadece DB boşsa)."""
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        if count > 0:
            return  # Zaten yüklü

        # Trendyol
        ty_path = os.path.join(FIXTURE_DIR, "trendyol_orders.json")
        with open(ty_path, encoding="utf-8") as f:
            ty_orders = json.load(f)
        _insert_orders(conn, ty_orders, "Trendyol")

        # Hepsiburada
        hb_path = os.path.join(FIXTURE_DIR, "hepsiburada_orders.json")
        with open(hb_path, encoding="utf-8") as f:
            hb_orders = json.load(f)
        _insert_orders(conn, hb_orders, "Hepsiburada")


def _insert_orders(conn, orders: list, marketplace: str):
    for o in orders:
        customer = o.get("customer", {})
        conn.execute(
            """INSERT OR IGNORE INTO orders
               (marketplace, marketplace_order_id, customer_name, customer_tax_id,
                is_company, customer_city, is_return,
                gross_amount, commission, shipping_cost, campaign_discount,
                net_payout, classify_status, order_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)""",
            (
                marketplace,
                o["marketplace_order_id"],
                customer.get("name", ""),
                customer.get("tax_id"),
                1 if customer.get("is_company") else 0,
                customer.get("city", ""),
                1 if o.get("is_return") else 0,
                o.get("gross_amount", 0),
                o.get("commission", 0),
                o.get("shipping_cost", 0),
                o.get("campaign_discount", 0),
                o.get("net_payout", 0),
                o.get("order_date", datetime.now().isoformat()),
            ),
        )
        order_id = conn.execute(
            "SELECT id FROM orders WHERE marketplace_order_id=?",
            (o["marketplace_order_id"],),
        ).fetchone()[0]

        for line in o.get("lines", []):
            conn.execute(
                """INSERT INTO order_lines
                   (order_id, product_name, category, barcode, quantity, unit_price)
                   VALUES (?,?,?,?,?,?)""",
                (
                    order_id,
                    line.get("product_name", ""),
                    line.get("category", ""),
                    line.get("barcode"),
                    line.get("quantity", 1),
                    line.get("unit_price", 0),
                ),
            )


# ── GET /api/orders ───────────────────────────────────────────────────────────

@router.get("/")
def list_orders():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY order_date DESC"
        ).fetchall()
        result = []
        for row in rows:
            order = dict(row)
            lines = conn.execute(
                "SELECT * FROM order_lines WHERE order_id=?", (order["id"],)
            ).fetchall()
            order["lines"] = [dict(l) for l in lines]
            result.append(order)
    return result


# ── POST /api/orders/{id}/classify ───────────────────────────────────────────

@router.post("/{order_id}/classify")
def classify_order(order_id: int):
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

        lines = conn.execute(
            "SELECT * FROM order_lines WHERE order_id=?", (order_id,)
        ).fetchall()

        results = []
        for line in lines:
            result = gemini_service.classify_kdv(
                line["product_name"], line["category"]
            )
            conn.execute(
                """UPDATE order_lines SET
                   gemini_kdv_rate=?, gemini_account_code=?, gemini_account_name=?,
                   gemini_reasoning=?, gemini_confidence=?
                   WHERE id=?""",
                (
                    result["kdv_orani"],
                    result["hesap_kodu"],
                    result["hesap_adi"],
                    result["gerekce"],
                    result["guven_skoru"],
                    line["id"],
                ),
            )
            results.append(result)

        conn.execute(
            "UPDATE orders SET classify_status='classified' WHERE id=?", (order_id,)
        )

    return {"order_id": order_id, "results": results}


# ── POST /api/orders/classify-all ────────────────────────────────────────────

@router.post("/classify-all")
def classify_all_orders():
    with get_db() as conn:
        pending = conn.execute(
            "SELECT id FROM orders WHERE classify_status='pending'"
        ).fetchall()

    pending_ids = [row["id"] for row in pending]

    classified = 0
    # Siparişler sırayla işlenir — gemini_service içindeki rate limiting
    # (2 sn bekleme + 429 retry) paralel çağrıda etkisiz olur, bu yüzden
    # asyncio.gather veya thread pool kullanılmaz.
    for order_id in pending_ids:
        try:
            classify_order(order_id)
            classified += 1
        except Exception as e:
            print(f"[classify-all] siparis {order_id} atlandı: {e}")

    return {"classified": classified, "total": len(pending_ids)}


# ── POST /api/orders/{id}/approve ────────────────────────────────────────────

@router.post("/{order_id}/approve")
def approve_order(order_id: int, body: ApproveRequest):
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

        approved_val = 1 if body.approved else 0
        conn.execute(
            """UPDATE order_lines SET user_approved=?, approved_at=?
               WHERE order_id=?""",
            (approved_val, datetime.now().isoformat(), order_id),
        )
        new_status = "approved" if body.approved else "rejected"
        conn.execute(
            "UPDATE orders SET classify_status=? WHERE id=?",
            (new_status, order_id),
        )

        invoice_id = None
        invoice_number = None

        # Onay verildi → otomatik taslak fatura oluştur
        if body.approved:
            existing = conn.execute(
                "SELECT id FROM invoices WHERE order_id=?", (order_id,)
            ).fetchone()

            if not existing:
                order_dict = dict(order)
                # Kurumsal müşteri → e-Fatura, bireysel → e-Arşiv
                invoice_type = "efatura" if order_dict.get("is_company") else "earsiv"

                invoice_number = _generate_invoice_number()
                conn.execute(
                    """INSERT INTO invoices (order_id, invoice_type, invoice_number, ubl_xml, status)
                       VALUES (?, ?, ?, '', 'draft')""",
                    (order_id, invoice_type, invoice_number),
                )
                invoice_id = conn.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]

    return {
        "order_id": order_id,
        "approved": body.approved,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
    }
