from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from database import get_db
from services import xml_service
from datetime import datetime
import random
import string

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


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
