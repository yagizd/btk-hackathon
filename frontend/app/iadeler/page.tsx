"use client";

import { useEffect, useState } from "react";
import { fetchReturns, classifyAllReturns, classifyReturn, ReturnItem } from "@/src/lib/api";
import Sidebar from "@/src/components/Sidebar";

const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });

const REASON_LABEL: Record<string, string> = {
  damaged:       "Hasarlı",
  wrong_item:    "Yanlış Ürün",
  size_fit:      "Beden / Uyumsuzluk",
  preference:    "Cayma / Beğenmedi",
  late_delivery: "Geç Teslim",
  quality:       "Kalite Sorunu",
  other:         "Diğer",
};

const REASON_BADGE: Record<string, string> = {
  damaged:       "bg-red-100 text-red-700",
  wrong_item:    "bg-orange-100 text-orange-700",
  size_fit:      "bg-amber-100 text-amber-700",
  preference:    "bg-slate-100 text-slate-700",
  late_delivery: "bg-purple-100 text-purple-700",
  quality:       "bg-rose-100 text-rose-700",
  other:         "bg-gray-100 text-gray-600",
};

const REFUND_LABEL: Record<string, string> = {
  cash_refund:    "Nakit İade",
  replacement:    "Değişim",
  partial_refund: "Kısmi İade",
  warranty:       "Garanti Kapsamı",
};

export default function IadelerPage() {
  const [items, setItems] = useState<ReturnItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [classifying, setClassifying] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reclassifyingId, setReclassifyingId] = useState<number | null>(null);

  async function load() {
    try {
      const data = await fetchReturns();
      setItems(data);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    setClassifying(true);
    classifyAllReturns()
      .catch((e) => console.error("returns/classify-all:", e))
      .finally(() => {
        setClassifying(false);
        load().finally(() => setLoading(false));
      });
  }, []);

  async function handleReclassify(orderId: number) {
    setReclassifyingId(orderId);
    try {
      await classifyReturn(orderId);
      await load();
    } catch (e) {
      alert(`Yeniden sınıflandırma hatası: ${(e as Error).message}`);
    } finally {
      setReclassifyingId(null);
    }
  }

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-4">İadeler</h1>

        {classifying && (
          <div className="flex items-center gap-2 mb-6 px-4 py-2.5 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-700 text-sm">
            <svg className="animate-spin h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            İade nedenleri Gemini ile sınıflandırılıyor…
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center h-40 text-gray-400">
            <svg className="animate-spin h-6 w-6 mr-2" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            İadeler yükleniyor…
          </div>
        ) : error ? (
          <div className="text-red-500 bg-red-50 rounded-lg p-4 text-sm">Hata: {error}</div>
        ) : items.length === 0 ? (
          <div className="text-gray-400 bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center text-sm">
            Bu dönemde iade kaydı bulunmuyor.
          </div>
        ) : (
          <div className="grid gap-4 max-w-4xl">
            {items.map((r) => {
              const reasonClass = r.reason ? REASON_BADGE[r.reason] ?? "bg-gray-100 text-gray-600" : "bg-gray-100 text-gray-400";
              const reasonLabel = r.reason ? REASON_LABEL[r.reason] ?? r.reason : "Henüz sınıflandırılmadı";
              const refundLabel = r.refund_category ? REFUND_LABEL[r.refund_category] ?? r.refund_category : "—";
              const lowConfidence = (r.gemini_confidence ?? 0) > 0 && (r.gemini_confidence ?? 0) < 0.75;

              return (
                <div key={r.order_id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
                  <div className="flex items-start justify-between mb-3 gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">
                          {r.marketplace}
                        </span>
                        <span className="font-mono text-xs text-gray-500">{r.marketplace_order_id}</span>
                      </div>
                      <h3 className="text-sm font-medium text-gray-800 truncate" title={r.product_name ?? ""}>
                        {r.product_name ?? "—"}
                      </h3>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {r.customer_name} · {r.customer_city ?? "—"} · {TRY.format(r.gross_amount)}
                      </p>
                    </div>
                    <button
                      onClick={() => handleReclassify(r.order_id)}
                      disabled={reclassifyingId === r.order_id}
                      className="text-xs px-3 py-1.5 border border-gray-200 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-50 shrink-0"
                    >
                      {reclassifyingId === r.order_id ? "…" : "Yeniden Sınıflandır"}
                    </button>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${reasonClass}`}>
                      {reasonLabel}
                    </span>
                    {r.refund_category && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                        {refundLabel}
                      </span>
                    )}
                    {r.kdv_adjustment_needed ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">
                        KDV Düzeltme Gerekli
                      </span>
                    ) : r.reason ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                        KDV Düzeltme Yok
                      </span>
                    ) : null}
                    {lowConfidence && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-50 text-yellow-700">
                        ⚠ Düşük güven ({r.gemini_confidence?.toFixed(2)})
                      </span>
                    )}
                  </div>

                  {r.gemini_explanation && (
                    <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3 text-xs text-gray-700 italic">
                      <span className="text-indigo-500 mr-1">✦</span>
                      {r.gemini_explanation}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
