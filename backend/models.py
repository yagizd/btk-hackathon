from pydantic import BaseModel
from typing import Optional, List


# ── Order Line ──────────────────────────────────────────────────────────────

class OrderLineOut(BaseModel):
    id: int
    order_id: int
    product_name: str
    category: str
    barcode: Optional[str]
    quantity: int
    unit_price: float
    gemini_kdv_rate: Optional[int]
    gemini_account_code: Optional[str]
    gemini_account_name: Optional[str]
    gemini_reasoning: Optional[str]
    gemini_confidence: Optional[float]
    user_approved: Optional[int]
    approved_at: Optional[str]


# ── Order ────────────────────────────────────────────────────────────────────

class OrderOut(BaseModel):
    id: int
    marketplace: str
    marketplace_order_id: str
    customer_name: str
    customer_tax_id: Optional[str]
    is_company: int
    customer_city: str
    is_return: int
    gross_amount: float
    commission: float
    shipping_cost: float
    campaign_discount: float
    net_payout: float
    classify_status: str
    order_date: str
    created_at: str
    lines: List[OrderLineOut] = []


# ── Approve ──────────────────────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    approved: bool  # True = onay, False = red


# ── Classify Result ──────────────────────────────────────────────────────────

class KDVResult(BaseModel):
    kdv_orani: int
    hesap_kodu: str
    hesap_adi: str
    gerekce: str
    guven_skoru: float


# ── Invoice ──────────────────────────────────────────────────────────────────

class InvoiceOut(BaseModel):
    id: int
    order_id: int
    invoice_type: str
    invoice_number: str
    status: str
    created_at: str


# ── Reconciliation ───────────────────────────────────────────────────────────

class ReconciliationOut(BaseModel):
    marketplace: str
    period: str
    expected_amount: float
    actual_amount: float
    difference: float
    gemini_explanation: Optional[str]
    status: str


# ── Dashboard Metrics ────────────────────────────────────────────────────────

class DashboardMetrics(BaseModel):
    total_gross: float
    total_commission: float
    total_net: float
    return_count: int
    order_count: int
    pending_classify: int
    pending_invoices: int


class DailyPoint(BaseModel):
    date: str
    gross: float
    net: float


# ── NL Query ─────────────────────────────────────────────────────────────────

class NLQueryRequest(BaseModel):
    question: str


class NLQueryResponse(BaseModel):
    answer: str
