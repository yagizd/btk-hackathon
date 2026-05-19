export const BASE_URL = "http://127.0.0.1:8000";

export interface LowConfidenceLine {
  line_id: number;
  product_name: string;
  gemini_kdv_rate?: number;
  gemini_confidence?: number;
  gemini_reasoning?: string;
}

export class LowConfidenceError extends Error {
  threshold: number;
  lines: LowConfidenceLine[];
  constructor(threshold: number, lines: LowConfidenceLine[], message?: string) {
    super(message ?? "Düşük güvenli satırlar var");
    this.name = "LowConfidenceError";
    this.threshold = threshold;
    this.lines = lines;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let body: unknown = null;
    try { body = await res.json(); } catch { /* non-JSON */ }
    const detail = (body as { detail?: unknown })?.detail;
    if (
      detail &&
      typeof detail === "object" &&
      (detail as { error?: string }).error === "low_confidence_lines"
    ) {
      const d = detail as { threshold: number; lines: LowConfidenceLine[]; message?: string };
      throw new LowConfidenceError(d.threshold, d.lines, d.message);
    }
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

export function fetchDashboard() {
  return request<DashboardMetrics>("/api/dashboard/metrics");
}

export function fetchOrders() {
  return request<Order[]>("/api/orders/");
}

export function approveOrder(orderId: string | number, forceLowConfidence = false) {
  return request(`/api/orders/${orderId}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved: true, force_low_confidence: forceLowConfidence }),
  });
}

export function classifyAll() {
  return request<{ classified: number; total: number }>("/api/orders/classify-all", {
    method: "POST",
  });
}

export function fetchUncertainOrders() {
  return request<Order[]>("/api/orders/uncertain");
}

export function classifyUncertain() {
  return request<{ processed: number; total: number }>("/api/orders/classify-uncertain", {
    method: "POST",
  });
}

export interface ExtractedLine {
  product_name: string;
  quantity: number;
  unit_price: number;
  kdv_orani: number;
  gerekce: string;
  guven_skoru: number;
}

export interface ExtractedInvoice {
  customer_name?: string;
  date?: string;
  lines: ExtractedLine[];
  gross_total?: number;
  extraction_confidence?: number;
  warnings?: string[];
  error?: string;
}

export async function uploadInvoiceImage(file: File): Promise<ExtractedInvoice> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE_URL}/api/orders/from-image`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body === "object" && "detail" in body) detail = String((body as { detail: unknown }).detail);
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export function saveExtractedOrder(body: {
  customer_name?: string;
  customer_city?: string;
  lines: ExtractedLine[];
  marketplace?: string;
  order_date?: string;
}) {
  return request<{ order_id: number; marketplace_order_id: string; line_count: number }>(
    "/api/orders/save-extracted",
    { method: "POST", body: JSON.stringify(body) }
  );
}

export function applyKdv(
  lineId: number,
  body: {
    kdv_orani: number;
    hesap_kodu?: string;
    hesap_adi?: string;
    gerekce?: string;
    source?: "primary" | "alternative" | "manual";
    approve?: boolean;
  }
) {
  return request<{ line_id: number; kdv_orani: number; approved: boolean }>(
    `/api/orders/lines/${lineId}/apply-kdv`,
    {
      method: "POST",
      body: JSON.stringify({ approve: true, source: "alternative", ...body }),
    }
  );
}

export function fetchInvoices() {
  return request<Invoice[]>("/api/invoices/");
}

export interface InvoiceSearchResult {
  filters: Record<string, string | number>;
  count: number;
  invoices: Invoice[];
}

export function searchInvoices(question: string) {
  return request<InvoiceSearchResult>("/api/invoices/search", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function fetchReconciliation() {
  return request<Reconciliation>("/api/reconciliation/");
}

export function nlQuery(question: string, sessionId?: string) {
  return request<{ answer: string; session_id: string }>("/api/nl-query", {
    method: "POST",
    body: JSON.stringify({ question, session_id: sessionId ?? null }),
  });
}

export function resetChatSession(sessionId: string) {
  return request<{ cleared: boolean }>(`/api/nl-query/${sessionId}`, { method: "DELETE" });
}

export function fetchReturns() {
  return request<ReturnItem[]>("/api/returns/");
}

export function classifyAllReturns() {
  return request<{ classified: number; total: number }>("/api/returns/classify-all", {
    method: "POST",
  });
}

export function classifyReturn(orderId: number) {
  return request<ReturnClassification>(`/api/returns/${orderId}/classify`, {
    method: "POST",
  });
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface KdvAlternative {
  kdv_orani: number;
  hesap_kodu: string;
  hesap_adi: string;
  gerekce: string;
  guven_skoru: number;
}

export interface OrderLine {
  id: number;
  order_id: number;
  product_name: string;
  category: string;
  barcode?: string;
  quantity: number;
  unit_price: number;
  gemini_kdv_rate?: number;
  gemini_account_code?: string;
  gemini_account_name?: string;
  gemini_reasoning?: string;
  gemini_confidence?: number;
  gemini_alternatives?: KdvAlternative[];
  user_approved?: number;
  approved_at?: string;
}

export interface Order {
  id: number;
  marketplace: string;
  marketplace_order_id: string;
  customer_name: string;
  customer_tax_id?: string;
  is_company: number;
  customer_city: string;
  is_return: number;
  gross_amount: number;
  commission: number;
  shipping_cost: number;
  campaign_discount: number;
  net_payout: number;
  classify_status: string;
  order_date: string;
  lines: OrderLine[];
}

export interface DashboardMetrics {
  total_gross: number;
  total_commission: number;
  total_net: number;
  return_count: number;
  order_count: number;
  pending_classify: number;
  pending_invoices: number;
}

export interface Invoice {
  id: number;
  order_id: number;
  invoice_type: string;       // "earsiv" | "efatura"
  invoice_number: string;
  status: string;             // "draft" | "sent" | "error"
  created_at: string;
  marketplace: string;
  marketplace_order_id: string;
  customer_name: string;
  gross_amount: number;
}

export interface PayoutLine {
  description: string;
  amount: number;
}

export interface ReturnClassification {
  reason: string;
  refund_category: string;
  kdv_adjustment_needed: boolean;
  explanation: string;
  confidence: number;
}

export interface ReturnItem {
  order_id: number;
  marketplace: string;
  marketplace_order_id: string;
  customer_name: string;
  customer_city?: string;
  gross_amount: number;
  order_date: string;
  product_name?: string;
  category?: string;
  reason?: string | null;
  refund_category?: string | null;
  kdv_adjustment_needed?: boolean | null;
  gemini_explanation?: string | null;
  gemini_confidence?: number | null;
  classified_at?: string | null;
}

export interface CommissionCheckItem {
  order_id?: string;
  category?: string;
  category_key: string;
  actual_rate: number;
  expected_band: [number, number];
  status: "normal" | "borderline" | "unusually_low" | "unusually_high";
}

export interface CommissionCheck {
  checks: CommissionCheckItem[];
  out_of_band_count: number;
  total: number;
}

export interface WaterfallLine {
  description: string;
  amount: number;
  line_type: "revenue" | "commission" | "campaign" | "shipping_support" | "return_refund" | "stopaj" | "adjustment" | "other";
  explanation: string;
  is_anomalous: boolean;
}

export interface Reconciliation {
  marketplace: string;
  period: string;
  expected_amount: number;
  actual_amount: number;
  difference: number;
  payout_lines: PayoutLine[];
  waterfall?: WaterfallLine[];
  gemini_explanation: string;
  severity?: "low" | "medium" | "high";
  root_cause?: string;
  suggested_action?: string;
  commission_check?: CommissionCheck;
  status: string;             // "reconciled" | "discrepancy"
}
