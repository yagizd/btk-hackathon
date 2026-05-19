"use client";

import { useEffect, useState } from "react";
import { fetchInvoices, searchInvoices, Invoice } from "@/src/lib/api";
import Sidebar from "@/src/components/Sidebar";


const STATUS_BADGE: Record<string, string> = {
  sent:  "bg-green-100 text-green-700",
  draft: "bg-yellow-100 text-yellow-700",
  error: "bg-red-100 text-red-700",
};

const STATUS_LABEL: Record<string, string> = {
  sent:  "Gönderildi",
  draft: "Taslak",
  error: "Hata",
};

const TYPE_LABEL: Record<string, string> = {
  earsiv:  "e-Arşiv",
  efatura: "e-Fatura",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function FaturalarPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Record<string, string | number> | null>(null);

  async function reloadAll() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchInvoices();
      setInvoices(data);
      setActiveFilters(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reloadAll();
  }, []);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setError(null);
    try {
      const res = await searchInvoices(q);
      setInvoices(res.invoices);
      setActiveFilters(res.filters);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans">
      <Sidebar />

      {/* Main content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-4">Faturalar</h1>

        {/* NL Search */}
        <form onSubmit={handleSearch} className="mb-6 flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Doğal dil ile ara — örn: 'Mayıs ayında Trendyol e-Fatura'"
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
            disabled={searching}
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={searching || !query.trim()}
              className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {searching ? "Aranıyor…" : "Gemini ile Ara"}
            </button>
            {activeFilters && (
              <button
                type="button"
                onClick={() => { setQuery(""); void reloadAll(); }}
                className="px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
              >
                Temizle
              </button>
            )}
          </div>
        </form>

        {activeFilters && Object.keys(activeFilters).length > 0 && (
          <div className="mb-4 p-3 bg-indigo-50 border border-indigo-100 rounded-lg flex flex-wrap items-center gap-2 text-xs">
            <span className="text-indigo-700 font-medium">✦ Gemini çıkarımı:</span>
            {Object.entries(activeFilters).map(([k, v]) => (
              <span key={k} className="px-2 py-0.5 bg-white rounded-full text-gray-700 font-mono">
                {k}={String(v)}
              </span>
            ))}
            <span className="text-gray-500 ml-auto">{invoices.length} sonuç</span>
          </div>
        )}
        {activeFilters && Object.keys(activeFilters).length === 0 && (
          <div className="mb-4 p-3 bg-amber-50 border border-amber-100 rounded-lg text-xs text-amber-800">
            Gemini sorgudan filtre çıkaramadı — tüm faturalar gösteriliyor.
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center h-40 text-gray-400">
            <svg className="animate-spin h-6 w-6 mr-2" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Faturalar yükleniyor…
          </div>
        ) : error ? (
          <div className="text-red-500 bg-red-50 rounded-lg p-4 text-sm">
            Hata: {error}
          </div>
        ) : invoices.length === 0 ? (
          <div className="text-gray-400 bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center text-sm">
            Henüz fatura oluşturulmamış.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl shadow-sm border border-gray-100">
            <table className="min-w-full bg-white text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Fatura No</th>
                  <th className="px-4 py-3 text-left">Sipariş ID</th>
                  <th className="px-4 py-3 text-left">Müşteri</th>
                  <th className="px-4 py-3 text-center">Tür</th>
                  <th className="px-4 py-3 text-center">Durum</th>
                  <th className="px-4 py-3 text-right">Tarih</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {invoices.map((inv) => {
                  const badgeClass = STATUS_BADGE[inv.status] ?? "bg-gray-100 text-gray-600";
                  return (
                    <tr key={inv.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{inv.invoice_number}</td>
                      <td className="px-4 py-3 text-gray-500 text-xs">{inv.marketplace_order_id}</td>
                      <td className="px-4 py-3 text-gray-700 max-w-[160px] truncate" title={inv.customer_name}>
                        {inv.customer_name}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
                          {TYPE_LABEL[inv.invoice_type] ?? inv.invoice_type}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${badgeClass}`}>
                          {STATUS_LABEL[inv.status] ?? inv.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-gray-500 text-xs whitespace-nowrap">
                        {formatDate(inv.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
