from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, Any
from database import get_db
from services import xml_service, gemini_service
from datetime import datetime, date
import random
import string

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

CONFIDENCE_THRESHOLD = 0.7


class InvoiceSearchRequest(BaseModel):
    question: str


def _generate_invoice_number() -> str:
    """PMX2026 + 9 haneli sıra numarası"""
    seq = "".join(random.choices(string.digits, k=9))
    return f"PMX2026{seq}"


@router.get("/")
def list_invoices():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT i.*, o.marketplace, o.marketplace_order_id,
                      o.customer_name, o.gross_amount
               FROM invoices i
               JOIN orders o ON o.id = i.order_id
               ORDER BY i.created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/{order_id}/generate")
def generate_invoice(order_id: int):
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

        order_dict = dict(order)

        # Kurumsal müşteri mi? → e-Fatura, değil → e-Arşiv
        invoice_type = "efatura" if order_dict.get("is_company") else "earsiv"

        # Zaten fatura var mı?
        existing = conn.execute(
            "SELECT id FROM invoices WHERE order_id=?", (order_id,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Bu sipariş için fatura zaten oluşturuldu")

        lines = conn.execute(
            "SELECT * FROM order_lines WHERE order_id=?", (order_id,)
        ).fetchall()
        lines_list = [dict(l) for l in lines]

        # Düşük güvenli + henüz onaylanmamış satır varsa fatura üretme
        ungated = [
            l for l in lines_list
            if l.get("gemini_confidence") is not None
            and l["gemini_confidence"] < CONFIDENCE_THRESHOLD
            and not l.get("user_approved")
        ]
        if ungated:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "low_confidence_lines",
                    "message": "Düşük güvenli satırlar onaylanmadan fatura kesilemez.",
                    "threshold": CONFIDENCE_THRESHOLD,
                    "lines": [
                        {
                            "line_id": l["id"],
                            "product_name": l["product_name"],
                            "gemini_kdv_rate": l.get("gemini_kdv_rate"),
                            "gemini_confidence": l.get("gemini_confidence"),
                            "gemini_reasoning": l.get("gemini_reasoning"),
                        }
                        for l in ungated
                    ],
                },
            )

        invoice_number = _generate_invoice_number()
        xml_content = xml_service.generate_ubl_xml(
            order=order_dict,
            lines=lines_list,
            invoice_number=invoice_number,
            invoice_type=invoice_type,
        )

        conn.execute(
            """INSERT INTO invoices (order_id, invoice_type, invoice_number, ubl_xml, status)
               VALUES (?,?,?,?,'draft')""",
            (order_id, invoice_type, invoice_number, xml_content),
        )
        invoice_id = conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "invoice_type": invoice_type,
        "status": "draft",
    }


_ALLOWED_FILTERS = {
    "marketplace",
    "status",
    "invoice_type",
    "customer_substring",
    "invoice_number_substring",
    "date_from",
    "date_to",
    "min_gross",
    "max_gross",
}


def _build_invoice_query(filters: dict) -> tuple[str, list]:
    """Parametreli SQL kurar; SQL injection olmaması için filtre keys whitelisted."""
    clauses = []
    params: list[Any] = []

    if "marketplace" in filters:
        clauses.append("o.marketplace = ?")
        params.append(str(filters["marketplace"]))
    if "status" in filters:
        clauses.append("i.status = ?")
        params.append(str(filters["status"]))
    if "invoice_type" in filters:
        clauses.append("i.invoice_type = ?")
        params.append(str(filters["invoice_type"]))
    if "customer_substring" in filters:
        clauses.append("LOWER(o.customer_name) LIKE LOWER(?)")
        params.append(f"%{filters['customer_substring']}%")
    if "invoice_number_substring" in filters:
        clauses.append("i.invoice_number LIKE ?")
        params.append(f"%{filters['invoice_number_substring']}%")
    if "date_from" in filters:
        clauses.append("DATE(i.created_at) >= DATE(?)")
        params.append(str(filters["date_from"]))
    if "date_to" in filters:
        clauses.append("DATE(i.created_at) <= DATE(?)")
        params.append(str(filters["date_to"]))
    if "min_gross" in filters:
        clauses.append("o.gross_amount >= ?")
        params.append(float(filters["min_gross"]))
    if "max_gross" in filters:
        clauses.append("o.gross_amount <= ?")
        params.append(float(filters["max_gross"]))

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        "SELECT i.*, o.marketplace, o.marketplace_order_id, o.customer_name, o.gross_amount "
        "FROM invoices i JOIN orders o ON o.id = i.order_id"
        + where
        + " ORDER BY i.created_at DESC"
    )
    return sql, params


@router.post("/search")
def search_invoices(body: InvoiceSearchRequest):
    """
    Doğal dil sorgusunu Gemini ile filtrelere çevirir, parametreli sorgu çalıştırır.
    Gemini ASLA SQL üretmez — yalnızca filtre değerleri çıkarır.
    """
    today = date.today().isoformat()
    raw_filters = gemini_service.parse_invoice_search_filters(body.question, today_iso=today)
    # whitelist + tip emniyeti
    filters = {k: v for k, v in raw_filters.items() if k in _ALLOWED_FILTERS}

    sql, params = _build_invoice_query(filters)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {
        "filters": filters,
        "count": len(rows),
        "invoices": [dict(r) for r in rows],
    }


@router.get("/{invoice_id}/xml")
def download_xml(invoice_id: int):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM invoices WHERE id=?", (invoice_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Fatura bulunamadı")

        xml_content = row["ubl_xml"]
        filename = f"{row['invoice_number']}.xml"

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
