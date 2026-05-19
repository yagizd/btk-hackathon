import json
import os
import random
import string
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from database import get_db
from models import OrderOut, OrderLineOut, ApproveRequest
from services import gemini_service


UNCERTAIN_THRESHOLD = 0.75


class ApplyKdvRequest(BaseModel):
    kdv_orani: int
    hesap_kodu: Optional[str] = None
    hesap_adi: Optional[str] = None
    gerekce: Optional[str] = None
    source: Optional[str] = "alternative"   # "alternative" | "manual" | "primary"
    approve: bool = True                    # apply + onayla


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
                    result.get("kdv_orani", 20),
                    result.get("hesap_kodu", "153"),
                    result.get("hesap_adi", "Ticari Mallar"),
                    result.get("gerekce", result.get("gemini_reasoning", "")),
                    result.get("guven_skoru", 0.80),
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
            print(f"[classify-all] siparis {order_id} atlandi: {str(e).encode('ascii', errors='replace').decode()}")

    return {"classified": classified, "total": len(pending_ids)}


# ── POST /api/orders/from-image (Vision OCR) ─────────────────────────────────

@router.post("/from-image")
async def order_from_image(file: UploadFile = File(...)):
    """
    Bir fatura/sipariş fotoğrafını Gemini multimodal ile işler.
    Yapılandırılmış kalem listesi + KDV önerileri döner. Henüz DB'ye yazılmaz —
    kullanıcı 'Kaydet' butonuyla onaylar.
    """
    content_type = (file.content_type or "image/jpeg").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Yalnız görsel dosyalar kabul edilir.")

    image_bytes = await file.read()
    # 8 MB sınırı (Gemini inline parts için makul üst sınır)
    if len(image_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dosya boyutu 8 MB'ı aşıyor.")

    result = gemini_service.extract_invoice_from_image(image_bytes, mime_type=content_type)
    return result


class SaveExtractedRequest(BaseModel):
    customer_name: str = ""
    customer_city: str = ""
    lines: list[dict] = []
    marketplace: str = "Manuel"
    order_date: Optional[str] = None


@router.post("/save-extracted")
def save_extracted_order(body: SaveExtractedRequest):
    """OCR ile çıkarılan kalemleri yeni bir manuel sipariş + sınıflandırılmış satırlar
    olarak DB'ye yazar. user_approved=0 — kullanıcı dashboard'dan onaylayabilir.
    """
    if not body.lines:
        raise HTTPException(status_code=400, detail="Kaydedilecek satır yok.")

    order_date = body.order_date or datetime.now().isoformat()
    marketplace_order_id = f"MNL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"
    gross = sum(float(l.get("quantity", 1)) * float(l.get("unit_price", 0)) for l in body.lines)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO orders
                 (marketplace, marketplace_order_id, customer_name, customer_city,
                  is_company, is_return, gross_amount, commission, net_payout,
                  classify_status, order_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                body.marketplace,
                marketplace_order_id,
                body.customer_name or "Manuel Müşteri",
                body.customer_city or "",
                0, 0, round(gross, 2), 0, round(gross, 2),
                "classified",
                order_date,
            ),
        )
        order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for l in body.lines:
            conn.execute(
                """INSERT INTO order_lines
                     (order_id, product_name, category, quantity, unit_price,
                      gemini_kdv_rate, gemini_account_code, gemini_account_name,
                      gemini_reasoning, gemini_confidence)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    order_id,
                    str(l.get("product_name", "")),
                    str(l.get("category", "OCR")),
                    int(l.get("quantity", 1) or 1),
                    float(l.get("unit_price", 0) or 0),
                    int(l.get("kdv_orani", 20)),
                    "153",
                    "Ticari Mallar",
                    str(l.get("gerekce", "")),
                    float(l.get("guven_skoru", 0.75)),
                ),
            )

    return {"order_id": order_id, "marketplace_order_id": marketplace_order_id, "line_count": len(body.lines)}


# ── GET /api/orders/uncertain ────────────────────────────────────────────────

@router.get("/uncertain")
def list_uncertain_orders():
    """
    Düşük güvenli (confidence < UNCERTAIN_THRESHOLD) ve henüz onaylanmamış satıra
    sahip siparişleri, mevcut alternatifleriyle birlikte döner.
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT o.*
               FROM orders o
               JOIN order_lines l ON l.order_id = o.id
               WHERE o.is_return = 0
                 AND l.gemini_confidence IS NOT NULL
                 AND l.gemini_confidence < ?
                 AND (l.user_approved IS NULL OR l.user_approved = 0)
               ORDER BY o.order_date DESC""",
            (UNCERTAIN_THRESHOLD,),
        ).fetchall()

        result = []
        for row in rows:
            order = dict(row)
            lines = conn.execute(
                "SELECT * FROM order_lines WHERE order_id=?", (order["id"],)
            ).fetchall()
            order_lines = []
            for l in lines:
                d = dict(l)
                alt_raw = d.get("gemini_alternatives")
                d["gemini_alternatives"] = json.loads(alt_raw) if alt_raw else []
                order_lines.append(d)
            order["lines"] = order_lines
            result.append(order)
    return result


# ── POST /api/orders/classify-uncertain ──────────────────────────────────────

@router.post("/classify-uncertain")
def classify_uncertain():
    """
    Tüm düşük güvenli + onaylanmamış satırlar için Gemini'den alternatifli yeniden
    öneri ister, primary + alternatives JSON'unu saklar.
    """
    with get_db() as conn:
        lines = conn.execute(
            """SELECT l.id, l.product_name, l.category
               FROM order_lines l
               JOIN orders o ON o.id = l.order_id
               WHERE o.is_return = 0
                 AND l.gemini_confidence IS NOT NULL
                 AND l.gemini_confidence < ?
                 AND (l.user_approved IS NULL OR l.user_approved = 0)""",
            (UNCERTAIN_THRESHOLD,),
        ).fetchall()

    processed = 0
    for l in lines:
        try:
            result = gemini_service.classify_kdv_with_alternatives(
                l["product_name"] or "", l["category"] or ""
            )
            primary = result["primary"]
            alts = result.get("alternatives", [])
            with get_db() as conn:
                conn.execute(
                    """UPDATE order_lines SET
                         gemini_kdv_rate=?, gemini_account_code=?, gemini_account_name=?,
                         gemini_reasoning=?, gemini_confidence=?, gemini_alternatives=?
                       WHERE id=?""",
                    (
                        primary["kdv_orani"],
                        primary["hesap_kodu"],
                        primary["hesap_adi"],
                        primary["gerekce"],
                        primary["guven_skoru"],
                        json.dumps(alts, ensure_ascii=False),
                        l["id"],
                    ),
                )
            processed += 1
        except Exception as e:
            print(f"[classify-uncertain] line {l['id']} atlandı: {str(e).encode('ascii','replace').decode()}")

    return {"processed": processed, "total": len(lines)}


# ── POST /api/order-lines/{line_id}/apply-kdv ────────────────────────────────

@router.post("/lines/{line_id}/apply-kdv")
def apply_kdv(line_id: int, body: ApplyKdvRequest):
    """Satır için seçilen KDV oranını uygular + opsiyonel olarak onaylar."""
    with get_db() as conn:
        line = conn.execute(
            "SELECT id, order_id FROM order_lines WHERE id=?", (line_id,)
        ).fetchone()
        if not line:
            raise HTTPException(status_code=404, detail="Satır bulunamadı")

        approved = 1 if body.approve else 0
        approved_at = datetime.now().isoformat() if body.approve else None

        conn.execute(
            """UPDATE order_lines SET
                 gemini_kdv_rate=?,
                 gemini_account_code=COALESCE(?, gemini_account_code),
                 gemini_account_name=COALESCE(?, gemini_account_name),
                 gemini_reasoning=COALESCE(?, gemini_reasoning),
                 gemini_confidence=CASE WHEN ?=1 THEN 1.0 ELSE gemini_confidence END,
                 user_approved=?,
                 approved_at=?
               WHERE id=?""",
            (
                body.kdv_orani,
                body.hesap_kodu,
                body.hesap_adi,
                body.gerekce,
                approved,
                approved,
                approved_at,
                line_id,
            ),
        )

        # Tüm satırlar onaylandıysa sipariş statüsünü 'approved' yap
        if body.approve:
            order_id = line["order_id"]
            pending_count = conn.execute(
                """SELECT COUNT(*) FROM order_lines
                   WHERE order_id=? AND (user_approved IS NULL OR user_approved=0)""",
                (order_id,),
            ).fetchone()[0]
            if pending_count == 0:
                conn.execute(
                    "UPDATE orders SET classify_status='approved' WHERE id=?", (order_id,)
                )

    return {"line_id": line_id, "kdv_orani": body.kdv_orani, "approved": body.approve}


# ── POST /api/orders/{id}/approve ────────────────────────────────────────────

CONFIDENCE_THRESHOLD = 0.7


@router.post("/{order_id}/approve")
def approve_order(order_id: int, body: ApproveRequest):
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

        # Confidence-gated: pozitif onay için düşük güvenli satırlar açıkça onaylanmalı
        if body.approved and not body.force_low_confidence:
            low_lines = conn.execute(
                """SELECT id, product_name, gemini_kdv_rate, gemini_confidence, gemini_reasoning
                   FROM order_lines
                   WHERE order_id=? AND gemini_confidence IS NOT NULL
                     AND gemini_confidence < ?""",
                (order_id, CONFIDENCE_THRESHOLD),
            ).fetchall()
            if low_lines:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "low_confidence_lines",
                        "message": "Düşük güvenli satırlar var; onaylamak için force_low_confidence=true gönderin.",
                        "threshold": CONFIDENCE_THRESHOLD,
                        "lines": [
                            {
                                "line_id": l["id"],
                                "product_name": l["product_name"],
                                "gemini_kdv_rate": l["gemini_kdv_rate"],
                                "gemini_confidence": l["gemini_confidence"],
                                "gemini_reasoning": l["gemini_reasoning"],
                            }
                            for l in low_lines
                        ],
                    },
                )

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
