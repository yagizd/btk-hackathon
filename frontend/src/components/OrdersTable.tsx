"use client";

import { useEffect, useState } from "react";
import {
  fetchOrders,
  approveOrder,
  Order,
  LowConfidenceError,
  LowConfidenceLine,
  BASE_URL,
} from "@/src/lib/api";

const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });

const KDV_BADGE: Record<number, string> = {
  20: "bg-green-100 text-green-700",
  10: "bg-yellow-100 text-yellow-700",
  1: "bg-blue-100 text-blue-700",
};

export default function OrdersTable() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Onay state'leri
  const [approving, setApproving] = useState<Set<number>>(new Set());
  const [approved, setApproved] = useState<Set<number>>(new Set());

  // Fatura state'leri
  const [invoicing, setInvoicing] = useState<Set<number>>(new Set());
  const [invoiced, setInvoiced] = useState<Set<number>>(new Set());

  // Düşük güven onay modali
  const [lowConfirm, setLowConfirm] = useState<{
    order: Order;
    lines: LowConfidenceLine[];
    threshold: number;
  } | null>(null);

  useEffect(() => {
    fetchOrders()
      .then((data) => setOrders(data.filter((o) => !o.is_return)))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function doApprove(order: Order, force: boolean) {
    setApproving((prev) => new Set(prev).add(order.id));
    try {
      await approveOrder(order.id, force);
      setApproved((prev) => new Set(prev).add(order.id));
      setLowConfirm(null);
    } catch (e) {
      if (e instanceof LowConfidenceError) {
        setLowConfirm({ order, lines: e.lines, threshold: e.threshold });
      } else {
        alert(`Onaylama hatası: ${(e as Error).message}`);
      }
    } finally {
      setApproving((prev) => {
        const next = new Set(prev);
        next.delete(order.id);
        return next;
      });
    }
  }

  function handleApprove(order: Order) {
    void doApprove(order, false);
  }

  async function handleGenerateInvoice(order: Order) {
    setInvoicing((prev) => new Set(prev).add(order.id));
    try {
      const res = await fetch(`${BASE_URL}/api/invoices/${order.id}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      setInvoiced((prev) => new Set(prev).add(order.id));
    } catch (e) {
      alert(`Fatura oluşturulamadı: ${(e as Error).message}`);
    } finally {
      setInvoicing((prev) => {
        const next = new Set(prev);
        next.delete(order.id);
        return next;
      });
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-400">
        <svg className="animate-spin h-6 w-6 mr-2" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        Siparişler yükleniyor…
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-red-500 bg-red-50 rounded-lg p-4 text-sm">
        Hata: {error}
      </div>
    );
  }

  return (
    <>
    {lowConfirm && (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div className="bg-white rounded-xl shadow-xl border border-gray-100 max-w-lg w-full p-6">
          <div className="flex items-start gap-3 mb-4">
            <svg className="w-6 h-6 text-amber-500 shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.72-1.36 3.485 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-5a1 1 0 00-1 1v2a1 1 0 002 0V9a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <div>
              <h3 className="text-base font-semibold text-gray-800">Düşük Güvenli Satırlar</h3>
              <p className="text-sm text-gray-600 mt-1">
                Bu sipariş için Gemini'nin güven skoru %{(lowConfirm.threshold * 100).toFixed(0)} altında.
                Onaylamak için aşağıdaki KDV önerilerini gözden geçirin.
              </p>
            </div>
          </div>
          <div className="space-y-2 max-h-64 overflow-y-auto mb-4">
            {lowConfirm.lines.map((l) => (
              <div key={l.line_id} className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-gray-800 truncate" title={l.product_name}>{l.product_name}</span>
                  <span className="text-xs font-mono text-amber-700 shrink-0 ml-2">
                    KDV %{l.gemini_kdv_rate ?? "—"} · {l.gemini_confidence?.toFixed(2) ?? "—"}
                  </span>
                </div>
                {l.gemini_reasoning && (
                  <p className="text-xs text-gray-600 mt-1 italic">"{l.gemini_reasoning}"</p>
                )}
              </div>
            ))}
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setLowConfirm(null)}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
            >
              Vazgeç
            </button>
            <button
              onClick={() => doApprove(lowConfirm.order, true)}
              disabled={approving.has(lowConfirm.order.id)}
              className="px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded-lg hover:bg-amber-700 disabled:opacity-50"
            >
              {approving.has(lowConfirm.order.id) ? "Onaylanıyor…" : "Yine de Onayla"}
            </button>
          </div>
        </div>
      </div>
    )}
    <div className="overflow-x-auto rounded-xl shadow-sm border border-gray-100">
      <table className="min-w-full bg-white text-sm">
        <thead>
          <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wide">
            <th className="px-4 py-3 text-left">Pazaryeri</th>
            <th className="px-4 py-3 text-left">Ürün Adı</th>
            <th className="px-4 py-3 text-right">Brüt Tutar</th>
            <th className="px-4 py-3 text-center">KDV Önerisi</th>
            <th className="px-4 py-3 text-center">Güven Skoru</th>
            <th className="px-4 py-3 text-center">Onay</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {orders.map((order) => {
            const firstLine = order.lines?.[0];
            const kdvRate = firstLine?.gemini_kdv_rate;
            const confidence = firstLine?.gemini_confidence ?? 0;
            const productName = firstLine?.product_name ?? order.marketplace_order_id;
            const lowConfidence = confidence > 0 && confidence < 0.8;
            const isApproved = approved.has(order.id) || order.classify_status === "approved";
            const isApproving = approving.has(order.id);
            const isInvoicing = invoicing.has(order.id);
            const isInvoiced = invoiced.has(order.id);
            const badgeClass = kdvRate != null ? (KDV_BADGE[kdvRate] ?? "bg-gray-100 text-gray-600") : "bg-gray-100 text-gray-400";

            return (
              <tr
                key={order.id}
                className={
                  isApproved
                    ? "bg-green-50"
                    : lowConfidence
                    ? "bg-yellow-50"
                    : "hover:bg-gray-50"
                }
              >
                <td className="px-4 py-3 font-medium text-gray-700">{order.marketplace}</td>
                <td className="px-4 py-3 text-gray-600 max-w-[200px] truncate" title={productName}>
                  {productName}
                </td>
                <td className="px-4 py-3 text-right font-mono text-gray-800">
                  {TRY.format(order.gross_amount)}
                </td>
                <td className="px-4 py-3 text-center">
                  {kdvRate != null ? (
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${badgeClass}`}>
                      %{kdvRate}
                    </span>
                  ) : (
                    <span className="text-gray-300 text-xs">—</span>
                  )}
                  {firstLine?.gemini_reasoning && (
                    <span className="ml-2 text-xs text-gray-500 italic">
                      "{firstLine.gemini_reasoning}"
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-center">
                  {confidence > 0 ? (
                    <span
                      className={`inline-flex items-center gap-1 text-xs font-medium ${
                        lowConfidence ? "text-yellow-700" : "text-gray-600"
                      }`}
                      title={lowConfidence ? "Manuel kontrol et" : undefined}
                    >
                      {lowConfidence && (
                        <svg className="w-3.5 h-3.5 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.72-1.36 3.485 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-5a1 1 0 00-1 1v2a1 1 0 002 0V9a1 1 0 00-1-1z" clipRule="evenodd" />
                        </svg>
                      )}
                      {confidence.toFixed(2)}
                    </span>
                  ) : (
                    <span className="text-gray-300 text-xs">—</span>
                  )}
                </td>

                {/* Onay kolonu — 3 farklı durum */}
                <td className="px-4 py-3 text-center">
                  {isInvoiced ? (
                    // Fatura kesildi
                    <span className="text-green-600 font-semibold text-xs">✓ Fatura Kesildi</span>
                  ) : isApproved ? (
                    // Onaylı → Fatura Kes butonu
                    <button
                      onClick={() => handleGenerateInvoice(order)}
                      disabled={isInvoicing}
                      className="px-3 py-1 bg-emerald-600 text-white text-xs rounded-md hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {isInvoicing ? "Kesiliyor…" : "Fatura Kes"}
                    </button>
                  ) : (
                    // Henüz onaylanmamış → Onayla butonu
                    <button
                      onClick={() => handleApprove(order)}
                      disabled={isApproving}
                      className="px-3 py-1 bg-indigo-600 text-white text-xs rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {isApproving ? "…" : "Onayla"}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    </>
  );
}
