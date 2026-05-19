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

    # DB'deki Trendyol siparişlerinden beklenen tutarı + komisyon kontrolü için detay
    with get_db() as conn:
        rows = conn.execute(
            """SELECT o.id, o.net_payout, o.is_return, o.marketplace_order_id,
                      o.gross_amount, o.commission,
                      (SELECT category FROM order_lines WHERE order_id=o.id LIMIT 1) as category
               FROM orders o
               WHERE o.marketplace='Trendyol'"""
        ).fetchall()

    order_summary = []
    expected = 0.0
    for row in rows:
        net = row["net_payout"]
        expected += net
        order_summary.append({
            "order_id": row["marketplace_order_id"],
            "net_payout": net,
            "gross_amount": row["gross_amount"],
            "commission": row["commission"],
            "category": row["category"] or "",
            "is_return": bool(row["is_return"]),
        })

    difference = round(actual_payout - expected, 2)

    # Gemini analizi (structured output: explanation + severity + root_cause + action + commission_check)
    analysis = gemini_service.explain_reconciliation(
        expected_amount=expected,
        actual_amount=actual_payout,
        difference=difference,
        payout_json=payout_data,
        order_summary=order_summary,
        marketplace="Trendyol",
    )

    # Payout waterfall: her kaleme açıklama + anomaly flag
    waterfall = gemini_service.analyze_payout_waterfall(
        payout_lines=payout_data.get("payout_lines", []),
        marketplace="Trendyol",
    )

    return {
        "marketplace": "Trendyol",
        "period": payout_data.get("period", "Mayıs 2026"),
        "expected_amount": round(expected, 2),
        "actual_amount": actual_payout,
        "difference": difference,
        "payout_lines": payout_data.get("payout_lines", []),
        "waterfall": waterfall,
        "gemini_explanation": analysis.get("explanation"),
        "severity": analysis.get("severity"),
        "root_cause": analysis.get("root_cause"),
        "suggested_action": analysis.get("suggested_action"),
        "commission_check": analysis.get("commission_check"),
        "status": "reconciled" if abs(difference) < 1 else "discrepancy",
    }
