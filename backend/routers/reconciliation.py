import json
import os
from fastapi import APIRouter
from database import get_db
from services import gemini_service

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixture_data")


@router.get("/")
def get_reconciliation():
    # Fixture payout verisini yükle
    payout_path = os.path.join(FIXTURE_DIR, "trendyol_payout.json")
    with open(payout_path, encoding="utf-8") as f:
        payout_data = json.load(f)

    actual_payout = payout_data["actual_payout"]

    # DB'deki Trendyol siparişlerinden beklenen tutarı hesapla
    with get_db() as conn:
        rows = conn.execute(
            """SELECT net_payout, is_return, marketplace_order_id
               FROM orders WHERE marketplace='Trendyol'"""
        ).fetchall()

    order_summary = []
    expected = 0.0
    for row in rows:
        net = row["net_payout"]
        expected += net
        order_summary.append({
            "order_id": row["marketplace_order_id"],
            "net_payout": net,
            "is_return": bool(row["is_return"]),
        })

    difference = round(actual_payout - expected, 2)

    # Gemini açıklaması
    explanation = gemini_service.explain_reconciliation(
        expected_amount=expected,
        actual_amount=actual_payout,
        difference=difference,
        payout_json=payout_data,
        order_summary=order_summary,
    )

    return {
        "marketplace": "Trendyol",
        "period": payout_data.get("period", "Mayıs 2026"),
        "expected_amount": round(expected, 2),
        "actual_amount": actual_payout,
        "difference": difference,
        "payout_lines": payout_data.get("payout_lines", []),
        "gemini_explanation": explanation,
        "status": "reconciled" if abs(difference) < 1 else "discrepancy",
    }
