"use client";

import { useRef, useState } from "react";
import Sidebar from "@/src/components/Sidebar";
import {
  uploadInvoiceImage,
  saveExtractedOrder,
  ExtractedInvoice,
  ExtractedLine,
} from "@/src/lib/api";

const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });

const KDV_COLOR: Record<number, string> = {
  1:  "bg-blue-100 text-blue-700",
  10: "bg-amber-100 text-amber-700",
  20: "bg-emerald-100 text-emerald-700",
};

export default function YuklePage() {
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [extracted, setExtracted] = useState<ExtractedInvoice | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedOrderId, setSavedOrderId] = useState<number | null>(null);
  const [customerName, setCustomerName] = useState("");
  const [customerCity, setCustomerCity] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function reset() {
    setImagePreview(null);
    setExtracted(null);
    setError(null);
    setSavedOrderId(null);
    setCustomerName("");
    setCustomerCity("");
    if (inputRef.current) inputRef.current.value = "";
  }

  async function handleFile(f: File) {
    setError(null);
    setExtracted(null);
    setSavedOrderId(null);
    setImagePreview(URL.createObjectURL(f));
    setExtracting(true);
    try {
      const result = await uploadInvoiceImage(f);
      setExtracted(result);
      if (result.customer_name) setCustomerName(result.customer_name);
      if (result.error) setError(result.error);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExtracting(false);
    }
  }

  function updateLine(i: number, patch: Partial<ExtractedLine>) {
    setExtracted((prev) => {
      if (!prev) return prev;
      const lines = prev.lines.map((l, idx) => (idx === i ? { ...l, ...patch } : l));
      return { ...prev, lines };
    });
  }

  function removeLine(i: number) {
    setExtracted((prev) => prev ? { ...prev, lines: prev.lines.filter((_, idx) => idx !== i) } : prev);
  }

  async function handleSave() {
    if (!extracted || extracted.lines.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const res = await saveExtractedOrder({
        customer_name: customerName,
        customer_city: customerCity,
        lines: extracted.lines,
        order_date: extracted.date,
      });
      setSavedOrderId(res.order_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const grossEstimate = extracted?.lines.reduce(
    (s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0),
    0
  ) ?? 0;

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans">
      <Sidebar />
      <main className="flex-1 p-8 overflow-y-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">Fatura Yükle (Vision OCR)</h1>
        <p className="text-sm text-gray-500 mb-6">
          Kağıt faturanın fotoğrafını yükleyin — Gemini multimodal kalemleri ve KDV önerilerini çıkarsın.
        </p>

        {!imagePreview ? (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = e.dataTransfer.files?.[0];
              if (f) void handleFile(f);
            }}
            onClick={() => inputRef.current?.click()}
            className={`max-w-2xl border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
              dragOver ? "border-indigo-400 bg-indigo-50" : "border-gray-200 hover:bg-gray-50"
            }`}
          >
            <svg className="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            <p className="text-sm text-gray-600">Bir görüntüyü sürükle veya tıkla</p>
            <p className="text-xs text-gray-400 mt-1">JPG, PNG, WEBP — maks. 8 MB</p>
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleFile(f);
              }}
            />
          </div>
        ) : (
          <div className="grid lg:grid-cols-2 gap-6 max-w-6xl">
            {/* Image preview */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-700">Yüklenen Görsel</h3>
                <button
                  onClick={reset}
                  className="text-xs text-gray-500 hover:text-gray-700 underline"
                >
                  Sıfırla
                </button>
              </div>
              <img
                src={imagePreview}
                alt="invoice"
                className="rounded-lg max-h-[600px] mx-auto object-contain"
              />
            </div>

            {/* Extracted */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <span className="text-indigo-500">✦</span> Gemini Çıkarımı
              </h3>

              {extracting && (
                <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Görsel analiz ediliyor… (~5–10 sn)
                </div>
              )}

              {error && (
                <div className="text-red-600 bg-red-50 rounded-lg p-3 text-xs mb-3">{error}</div>
              )}

              {extracted && !extracting && (
                <>
                  {/* Header info */}
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    <div>
                      <label className="text-xs text-gray-500">Müşteri</label>
                      <input
                        type="text"
                        value={customerName}
                        onChange={(e) => setCustomerName(e.target.value)}
                        className="w-full mt-0.5 text-sm border border-gray-200 rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500">Şehir</label>
                      <input
                        type="text"
                        value={customerCity}
                        onChange={(e) => setCustomerCity(e.target.value)}
                        className="w-full mt-0.5 text-sm border border-gray-200 rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                      />
                    </div>
                  </div>

                  {/* Confidence + warnings */}
                  <div className="flex flex-wrap items-center gap-2 mb-3 text-xs">
                    {extracted.extraction_confidence != null && (
                      <span className={`px-2 py-0.5 rounded-full ${
                        extracted.extraction_confidence >= 0.8 ? "bg-emerald-50 text-emerald-700" :
                        extracted.extraction_confidence >= 0.5 ? "bg-amber-50 text-amber-700" :
                        "bg-red-50 text-red-700"
                      }`}>
                        Okunabilirlik: {(extracted.extraction_confidence * 100).toFixed(0)}%
                      </span>
                    )}
                    {extracted.date && (
                      <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 font-mono">
                        {extracted.date}
                      </span>
                    )}
                  </div>

                  {extracted.warnings && extracted.warnings.length > 0 && (
                    <ul className="bg-amber-50 border border-amber-100 rounded-lg p-2 text-xs text-amber-800 mb-3 space-y-1">
                      {extracted.warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}
                    </ul>
                  )}

                  {/* Lines */}
                  {extracted.lines.length === 0 ? (
                    <div className="text-sm text-gray-400 italic py-4 text-center">
                      Çıkarılabilir kalem bulunamadı.
                    </div>
                  ) : (
                    <div className="space-y-2 mb-3 max-h-96 overflow-y-auto pr-1">
                      {extracted.lines.map((line, i) => (
                        <div key={i} className="bg-gray-50 rounded-lg p-3">
                          <div className="flex items-start gap-2">
                            <input
                              type="text"
                              value={line.product_name}
                              onChange={(e) => updateLine(i, { product_name: e.target.value })}
                              className="flex-1 text-sm bg-white border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                            />
                            <button
                              onClick={() => removeLine(i)}
                              className="text-xs text-red-500 hover:text-red-700"
                              title="Satırı sil"
                            >
                              ✕
                            </button>
                          </div>
                          <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
                            <div>
                              <label className="text-gray-500">Adet</label>
                              <input
                                type="number"
                                value={line.quantity}
                                onChange={(e) => updateLine(i, { quantity: Number(e.target.value) || 0 })}
                                className="w-full bg-white border border-gray-200 rounded px-2 py-1 font-mono"
                              />
                            </div>
                            <div>
                              <label className="text-gray-500">Birim Fiyat</label>
                              <input
                                type="number"
                                step="0.01"
                                value={line.unit_price}
                                onChange={(e) => updateLine(i, { unit_price: Number(e.target.value) || 0 })}
                                className="w-full bg-white border border-gray-200 rounded px-2 py-1 font-mono"
                              />
                            </div>
                            <div>
                              <label className="text-gray-500">KDV</label>
                              <select
                                value={line.kdv_orani}
                                onChange={(e) => updateLine(i, { kdv_orani: Number(e.target.value) })}
                                className={`w-full bg-white border border-gray-200 rounded px-2 py-1 font-medium ${KDV_COLOR[line.kdv_orani] ?? ""}`}
                              >
                                <option value={1}>%1</option>
                                <option value={10}>%10</option>
                                <option value={20}>%20</option>
                              </select>
                            </div>
                          </div>
                          {line.gerekce && (
                            <p className="text-xs text-gray-500 italic mt-2">"{line.gerekce}"</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex items-center justify-between border-t border-gray-100 pt-3 mb-3">
                    <span className="text-sm text-gray-600">Toplam (tahmin)</span>
                    <span className="font-mono font-semibold text-gray-800">{TRY.format(grossEstimate)}</span>
                  </div>

                  {savedOrderId ? (
                    <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-3 text-sm text-emerald-700">
                      ✓ Sipariş #{savedOrderId} olarak kaydedildi. Dashboard'dan onaylayıp fatura kesebilirsiniz.
                    </div>
                  ) : (
                    <button
                      onClick={handleSave}
                      disabled={saving || extracted.lines.length === 0}
                      className="w-full px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {saving ? "Kaydediliyor…" : "Sipariş Olarak Kaydet"}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
