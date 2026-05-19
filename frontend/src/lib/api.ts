const BASE_URL = "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return res.json();
}

export function fetchDashboard() {
  return request<DashboardMetrics>("/api/dashboard/metrics");
}

export function fetchOrders() {
  return request<Order[]>("/api/orders/");
}

export function approveOrder(orderId: string | number) {
  return request(`/api/orders/${orderId}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved: true }),
  });
}

export function classifyAll() {
  return request<{ classified: number; total: number }>("/api/orders/classify-all", {
    method: "POST",
  });
}

export function fetchInvoices() {
  return request<Invoice[]>("/api/invoices/");
}

export function fetchReconciliation() {
  return request<Reconciliation>("/api/reconciliation/");
}

export function nlQuery(question: string) {
  return request<{ answer: string }>("/api/nl-query", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

// ── Types ─────────────────────────────────────────────────────────────────────

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

export interface Reconciliation {
  marketplace: string;
  period: string;
  expected_amount: number;
  actual_amount: number;
  difference: number;
  payout_lines: PayoutLine[];
  gemini_explanation: string;
  status: string;             // "reconciled" | "discrepancy"
}
