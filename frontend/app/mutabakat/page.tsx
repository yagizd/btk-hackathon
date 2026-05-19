"use client";

import { useEffect, useState } from "react";
import { fetchReconciliation, Reconciliation } from "@/src/lib/api";
import Sidebar from "@/src/components/Sidebar";
import PayoutWaterfall from "@/src/components/PayoutWaterfall";


const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });

const SEVERITY_STYLE: Record<string, { bg: string; border: string; text: string; label: string; icon: string }> = {
  low:    { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-800", label: "Düşük risk", icon: "●" },
  medium: { bg: "bg-amber-50",   border: "border-amber-200",   text: "text-amber-800",   label: "Orta risk",  icon: "▲" },
  high:   { bg: "bg-red-50",     border: "border-red-200",     text: "text-red-800",     label: "Yüksek risk", icon: "⚠" },
};

const ROOT_CAUSE_LABEL: Record<string, string> = {
  commission_outlier:  "Komisyon Sapması",
  campaign_kesinti:    "Kampanya Kesintisi",
  return_refund:       "İade Geri Ödemesi",
  stopaj_adjustment:   "Stopaj Düzenlemesi",
  missing_line_item:   "Eksik Kalem",
  rounding:            "Yuvarlama",
  multiple:            "Birden Fazla Neden",
  unknown:             "Belirsiz",
};

const COMM_STATUS_STYLE: Record<string, { dot: string; label: string }> = {
  normal:           { dot: "bg-emerald-500", label: "Normal" },
  borderline:       { dot: "bg-amber-400",   label: "Sınırda" },
  unusually_low:    { dot: "bg-blue-500",    label: "Beklenenin Altında" },
  unusually_high:   { dot: "bg-red-500",     label: "Beklenenin Üstünde" },
};

export default function MutabakatPage() {
  const [data, setData] = useState<Reconciliation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReconciliation()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans">
      <Sidebar />

      {/* Main content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Mutabakat</h1>

        {loading ? (
          <div className="flex items-center justify-center h-40 text-gray-400">
            <svg className="animate-spin h-6 w-6 mr-2" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Mutabakat verisi yükleniyor…
          </div>
        ) : error ? (
          <div className="text-red-500 bg-red-50 rounded-lg p-4 text-sm">
            Hata: {error}
          </div>
        ) : data ? (
          <div className="space-y-6 max-w-3xl">
            {/* Severity Banner */}
            {data.severity && (
              <div
                className={`rounded-xl border p-4 flex items-start gap-3 ${
                  SEVERITY_STYLE[data.severity].bg
                } ${SEVERITY_STYLE[data.severity].border}`}
              >
                <span className={`text-xl ${SEVERITY_STYLE[data.severity].text}`}>
                  {SEVERITY_STYLE[data.severity].icon}
                </span>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`font-semibold text-sm ${SEVERITY_STYLE[data.severity].text}`}>
                      {SEVERITY_STYLE[data.severity].label}
                    </span>
                    {data.root_cause && (
                      <span className={`text-xs px-2 py-0.5 rounded-full bg-white/60 ${SEVERITY_STYLE[data.severity].text}`}>
                        {ROOT_CAUSE_LABEL[data.root_cause] ?? data.root_cause}
                      </span>
                    )}
                  </div>
                  {data.suggested_action && (
                    <p className={`text-sm ${SEVERITY_STYLE[data.severity].text}`}>
                      <span className="font-medium">Önerilen aksiyon:</span> {data.suggested_action}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Özet Kart */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-semibold text-gray-800">{data.marketplace}</h2>
                  <p className="text-sm text-gray-500">{data.period}</p>
                </div>
                <span
                  className={`px-3 py-1 rounded-full text-xs font-semibold ${
                    data.status === "reconciled"
                      ? "bg-green-100 text-green-700"
                      : "bg-red-100 text-red-700"
                  }`}
                >
                  {data.status === "reconciled" ? "Mutabık" : "Fark Var"}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-4">
                {/* Beklenen */}
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-xs text-gray-500 mb-1">Beklenen Tutar</p>
                  <p className="text-lg font-bold text-gray-800">{TRY.format(data.expected_amount)}</p>
                </div>
                {/* Gerçekleşen */}
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-xs text-gray-500 mb-1">Gerçekleşen</p>
                  <p className="text-lg font-bold text-gray-800">{TRY.format(data.actual_amount)}</p>
                </div>
                {/* Fark */}
                <div
                  className={`rounded-lg p-4 ${
                    data.difference >= 0 ? "bg-green-50" : "bg-red-50"
                  }`}
                >
                  <p className="text-xs text-gray-500 mb-1">Fark</p>
                  <p
                    className={`text-lg font-bold ${
                      data.difference >= 0 ? "text-green-700" : "text-red-700"
                    }`}
                  >
                    {data.difference >= 0 ? "+" : ""}
                    {TRY.format(data.difference)}
                  </p>
                </div>
              </div>
            </div>

            {/* Gemini Açıklaması */}
            {data.gemini_explanation && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <span className="text-indigo-500">✦</span> Gemini Analizi
                </h3>
                <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">
                  {data.gemini_explanation}
                </p>
              </div>
            )}

            {/* Payout Waterfall (Gemini per-line analysis) */}
            {data.waterfall && data.waterfall.length > 0 && (
              <PayoutWaterfall lines={data.waterfall} />
            )}

            {/* Ödeme Kalemleri */}
            {data.payout_lines && data.payout_lines.length > 0 && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-4">Ödeme Kalemleri</h3>
                <div className="divide-y divide-gray-100">
                  {data.payout_lines.map((line, i) => (
                    <div key={i} className="flex items-center justify-between py-2.5">
                      <span className="text-sm text-gray-600">{line.description}</span>
                      <span
                        className={`text-sm font-mono font-medium ${
                          line.amount >= 0 ? "text-gray-800" : "text-red-600"
                        }`}
                      >
                        {line.amount >= 0 ? "" : "−"}
                        {TRY.format(Math.abs(line.amount))}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Komisyon Bandı Kontrolü */}
            {data.commission_check && data.commission_check.checks.length > 0 && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-700">Komisyon Bandı Kontrolü</h3>
                  <span className="text-xs text-gray-500">
                    {data.commission_check.out_of_band_count} / {data.commission_check.total} bant dışı
                  </span>
                </div>
                <div className="overflow-x-auto -mx-2">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-gray-500 text-xs uppercase tracking-wide">
                        <th className="px-2 py-2 text-left">Sipariş</th>
                        <th className="px-2 py-2 text-left">Kategori</th>
                        <th className="px-2 py-2 text-right">Komisyon</th>
                        <th className="px-2 py-2 text-right">Beklenen Bant</th>
                        <th className="px-2 py-2 text-left">Durum</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {data.commission_check.checks.map((c, i) => {
                        const style = COMM_STATUS_STYLE[c.status] ?? COMM_STATUS_STYLE.normal;
                        return (
                          <tr key={i} className={c.status === "unusually_high" || c.status === "unusually_low" ? "bg-red-50/40" : ""}>
                            <td className="px-2 py-2 font-mono text-xs text-gray-700">{c.order_id ?? "-"}</td>
                            <td className="px-2 py-2 text-gray-600 text-xs">{c.category ?? "-"}</td>
                            <td className="px-2 py-2 text-right font-mono text-xs text-gray-800">
                              %{(c.actual_rate * 100).toFixed(1)}
                            </td>
                            <td className="px-2 py-2 text-right font-mono text-xs text-gray-500">
                              %{(c.expected_band[0] * 100).toFixed(0)}–%{(c.expected_band[1] * 100).toFixed(0)}
                            </td>
                            <td className="px-2 py-2 text-xs">
                              <span className="inline-flex items-center gap-1.5">
                                <span className={`w-2 h-2 rounded-full ${style.dot}`} />
                                <span className="text-gray-700">{style.label}</span>
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </main>
    </div>
  );
}
