"use client";

import { useEffect, useState } from "react";
import {
  fetchUncertainOrders,
  classifyUncertain,
  applyKdv,
  Order,
  OrderLine,
  KdvAlternative,
} from "@/src/lib/api";

const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });

const KDV_COLOR: Record<number, string> = {
  1:  "bg-blue-100 text-blue-700",
  10: "bg-amber-100 text-amber-700",
  20: "bg-emerald-100 text-emerald-700",
};

function kdvBadge(rate: number) {
  return KDV_COLOR[rate] ?? "bg-gray-100 text-gray-600";
}

type OptionId = string;

function optionId(lineId: number, kdv: number, source: "primary" | "alternative") {
  return `${lineId}:${source}:${kdv}`;
}

export default function UncertainReview() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<number, OptionId>>({});
  const [applying, setApplying] = useState<Set<number>>(new Set());
  const [appliedLines, setAppliedLines] = useState<Set<number>>(new Set());

  async function load() {
    try {
      const data = await fetchUncertainOrders();
      setOrders(data);
      // Varsayılan seçim: birincil
      const defaults: Record<number, OptionId> = {};
      for (const o of data) {
        for (const l of o.lines) {
          if (l.gemini_kdv_rate != null) {
            defaults[l.id] = optionId(l.id, l.gemini_kdv_rate, "primary");
          }
        }
      }
      setSelected((prev) => ({ ...defaults, ...prev }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  async function handleComputeAlternatives() {
    setComputing(true);
    try {
      await classifyUncertain();
      await load();
    } catch (e) {
      alert(`Alternatif hesaplanamadı: ${(e as Error).message}`);
    } finally {
      setComputing(false);
    }
  }

  function buildPrimaryOption(line: OrderLine): KdvAlternative | null {
    if (line.gemini_kdv_rate == null) return null;
    return {
      kdv_orani: line.gemini_kdv_rate,
      hesap_kodu: line.gemini_account_code ?? "153",
      hesap_adi: line.gemini_account_name ?? "Ticari Mallar",
      gerekce: line.gemini_reasoning ?? "",
      guven_skoru: line.gemini_confidence ?? 0,
    };
  }

  function selectedOption(line: OrderLine): { source: "primary" | "alternative"; opt: KdvAlternative } | null {
    const sel = selected[line.id];
    if (!sel) return null;
    const [, source, kdvStr] = sel.split(":");
    const kdv = Number(kdvStr);
    if (source === "primary") {
      const p = buildPrimaryOption(line);
      return p ? { source: "primary", opt: p } : null;
    }
    const opt = (line.gemini_alternatives ?? []).find((a) => a.kdv_orani === kdv);
    return opt ? { source: "alternative", opt } : null;
  }

  async function handleApply(line: OrderLine) {
    const choice = selectedOption(line);
    if (!choice) return;
    setApplying((prev) => new Set(prev).add(line.id));
    try {
      await applyKdv(line.id, {
        kdv_orani: choice.opt.kdv_orani,
        hesap_kodu: choice.opt.hesap_kodu,
        hesap_adi: choice.opt.hesap_adi,
        gerekce: choice.opt.gerekce,
        source: choice.source,
        approve: true,
      });
      setAppliedLines((prev) => new Set(prev).add(line.id));
    } catch (e) {
      alert(`KDV uygulanamadı: ${(e as Error).message}`);
    } finally {
      setApplying((prev) => {
        const next = new Set(prev);
        next.delete(line.id);
        return next;
      });
    }
  }

  if (loading) {
    return (
      <div className="text-gray-400 text-sm py-4">Belirsiz öneriler yükleniyor…</div>
    );
  }
  if (error) {
    return <div className="text-red-500 bg-red-50 rounded-lg p-3 text-sm">Hata: {error}</div>;
  }
  if (orders.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 text-sm text-gray-500">
        Tüm sınıflandırmalar yeterli güven skoruna sahip — manuel inceleme gerektiren satır yok.
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-800">Manuel İnceleme Gereken Satırlar</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Gemini güveni %75 altında olan ve henüz onaylanmamış satırlar.
          </p>
        </div>
        <button
          onClick={handleComputeAlternatives}
          disabled={computing}
          className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
        >
          {computing ? "Alternatifler üretiliyor…" : "Alternatifleri Üret"}
        </button>
      </div>

      <div className="divide-y divide-gray-100">
        {orders.map((order) =>
          order.lines
            .filter((l) => (l.gemini_confidence ?? 1) < 0.75 && !l.user_approved)
            .map((line) => {
              const primary = buildPrimaryOption(line);
              const alts = line.gemini_alternatives ?? [];
              const sel = selected[line.id];
              const isApplied = appliedLines.has(line.id);
              const isApplying = applying.has(line.id);

              return (
                <div key={line.id} className="py-4">
                  <div className="flex items-start justify-between mb-2">
                    <div className="min-w-0 pr-3">
                      <div className="flex items-center gap-2 mb-1 text-xs">
                        <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-medium">
                          {order.marketplace}
                        </span>
                        <span className="font-mono text-gray-500">{order.marketplace_order_id}</span>
                        <span className="text-gray-400">·</span>
                        <span className="text-gray-500">{TRY.format(line.quantity * line.unit_price)}</span>
                      </div>
                      <p className="text-sm text-gray-800 font-medium truncate" title={line.product_name}>
                        {line.product_name}
                      </p>
                      <p className="text-xs text-gray-500">{line.category}</p>
                    </div>
                    <button
                      onClick={() => handleApply(line)}
                      disabled={isApplying || isApplied || !sel}
                      className={`text-xs px-3 py-1.5 rounded-md shrink-0 ${
                        isApplied
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                      }`}
                    >
                      {isApplied ? "✓ Uygulandı" : isApplying ? "…" : "Seçimi Uygula"}
                    </button>
                  </div>

                  <div className="grid gap-2 mt-2">
                    {primary && (
                      <KdvOption
                        opt={primary}
                        source="primary"
                        lineId={line.id}
                        checked={sel === optionId(line.id, primary.kdv_orani, "primary")}
                        onSelect={(v) => setSelected((p) => ({ ...p, [line.id]: v }))}
                      />
                    )}
                    {alts.map((a, i) => (
                      <KdvOption
                        key={i}
                        opt={a}
                        source="alternative"
                        lineId={line.id}
                        checked={sel === optionId(line.id, a.kdv_orani, "alternative")}
                        onSelect={(v) => setSelected((p) => ({ ...p, [line.id]: v }))}
                      />
                    ))}
                    {alts.length === 0 && (
                      <p className="text-xs text-gray-400 italic">
                        Henüz alternatif yok — "Alternatifleri Üret" butonuna basın.
                      </p>
                    )}
                  </div>
                </div>
              );
            })
        )}
      </div>
    </div>
  );
}

function KdvOption({
  opt,
  source,
  lineId,
  checked,
  onSelect,
}: {
  opt: KdvAlternative;
  source: "primary" | "alternative";
  lineId: number;
  checked: boolean;
  onSelect: (v: OptionId) => void;
}) {
  const id = optionId(lineId, opt.kdv_orani, source);
  return (
    <label
      className={`flex items-start gap-3 rounded-lg p-3 cursor-pointer border transition-colors ${
        checked ? "border-indigo-300 bg-indigo-50/40" : "border-gray-100 hover:bg-gray-50"
      }`}
    >
      <input
        type="radio"
        name={`kdv-${lineId}`}
        value={id}
        checked={checked}
        onChange={() => onSelect(id)}
        className="mt-1"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${kdvBadge(opt.kdv_orani)}`}>
            KDV %{opt.kdv_orani}
          </span>
          <span className="text-xs text-gray-500">{opt.hesap_kodu} · {opt.hesap_adi}</span>
          <span className="text-xs text-gray-400">·</span>
          <span className="text-xs text-gray-500">güven {opt.guven_skoru.toFixed(2)}</span>
          {source === "primary" && (
            <span className="text-[10px] uppercase tracking-wide text-indigo-600">Birincil</span>
          )}
        </div>
        {opt.gerekce && (
          <p className="text-xs text-gray-600 italic">"{opt.gerekce}"</p>
        )}
      </div>
    </label>
  );
}
