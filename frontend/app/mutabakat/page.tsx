"use client";

import { useEffect, useState } from "react";
import { fetchReconciliation, Reconciliation } from "@/src/lib/api";
import Sidebar from "@/src/components/Sidebar";


const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });

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
          </div>
        ) : null}
      </main>
    </div>
  );
}
