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
    force_low_confidence: Optional[bool] = False  # düşük güven uyarısını yok say


class LowConfidenceLine(BaseModel):
    line_id: int
    product_name: str
    gemini_kdv_rate: Optional[int]
    gemini_confidence: Optional[float]
    gemini_reasoning: Optional[str]


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

class CommissionCheckItem(BaseModel):
    order_id: Optional[str]
    category: Optional[str]
    category_key: str
    actual_rate: float
    expected_band: List[float]
    status: str  # normal | borderline | unusually_low | unusually_high


class CommissionCheck(BaseModel):
    checks: List[CommissionCheckItem]
    out_of_band_count: int
    total: int


class ReconciliationOut(BaseModel):
    marketplace: str
    period: str
    expected_amount: float
    actual_amount: float
    difference: float
    gemini_explanation: Optional[str]
    severity: Optional[str] = None       # low | medium | high
    root_cause: Optional[str] = None
    suggested_action: Optional[str] = None
    commission_check: Optional[CommissionCheck] = None
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
    session_id: Optional[str] = None


class NLQueryResponse(BaseModel):
    answer: str
    session_id: str


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    created_at: Optional[str] = None
