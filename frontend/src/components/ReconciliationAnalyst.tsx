"use client";

import { useState } from "react";
import {
  agentReconciliation,
  AgentTraceEntry,
  AgentReconciliationResponse,
  AgentUnreachableError,
} from "@/src/lib/api";

const TOOL_LABEL: Record<string, string> = {
  get_metrics:                    "📊 metrikler",
  list_orders:                    "📋 siparişler",
  get_top_products:               "🏆 top ürünler",
  check_reconciliation:           "💸 mutabakat",
  find_uncertain_classifications: "⚠️ belirsizler",
  get_invoice_by_number:          "📄 fatura",
  compute_kdv_breakdown:          "🧮 KDV dağılımı",
  get_returns_summary:            "↩️ iadeler",
};

interface Step {
  index: number;
  toolName: string;
  args: Record<string, unknown>;
  result: unknown;
  note?: string;
}

function buildSteps(trace: AgentTraceEntry[]): { plan?: string; steps: Step[] } {
  // İlk model_note (varsa) plan olarak kabul edilir.
  let plan: string | undefined;
  for (const e of trace) {
    if (e.type === "model_note" && !plan) {
      plan = e.content;
      break;
    }
  }
  const steps: Step[] = [];
  let pending: { name: string; args: Record<string, unknown> } | null = null;
  let lastNoteAfterResult: string | undefined;
  for (const e of trace) {
    if (e.type === "tool_call") {
      pending = { name: e.name, args: e.args };
    } else if (e.type === "tool_result" && pending && pending.name === e.name) {
      steps.push({
        index: steps.length + 1,
        toolName: pending.name,
        args: pending.args,
        result: e.result,
        note: lastNoteAfterResult,
      });
      pending = null;
      lastNoteAfterResult = undefined;
    } else if (e.type === "model_note") {
      // Adım sırasındaki ek notlar
      if (steps.length > 0 && !pending) {
        steps[steps.length - 1].note = e.content;
      }
    }
  }
  return { plan, steps };
}

function summarizeResult(r: unknown): string {
  if (r == null) return "—";
  if (typeof r === "object") {
    const o = r as Record<string, unknown>;
    if ("error" in o) return `❌ ${String(o.error)}`;
    const keys = Object.keys(o);
    const interesting = keys.filter((k) => typeof o[k] === "number" || typeof o[k] === "string").slice(0, 4);
    if (interesting.length > 0) {
      return interesting.map((k) => `${k}=${String(o[k])}`).join(" · ");
    }
    if ("count" in o) return `${o.count} kayıt`;
    return `${keys.length} alan`;
  }
  return String(r);
}

export default function ReconciliationAnalyst({ marketplace = "Trendyol" }: { marketplace?: string }) {
  const [data, setData] = useState<AgentReconciliationResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; upstream?: string; trace?: AgentTraceEntry[] } | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setData(null);
    setOpen(true);
    try {
      const res = await agentReconciliation(marketplace);
      setData(res);
    } catch (e) {
      if (e instanceof AgentUnreachableError) {
        setError({ message: e.message, upstream: e.upstream, trace: e.trace });
      } else {
        setError({ message: (e as Error).message });
      }
    } finally {
      setLoading(false);
    }
  }

  if (!open) {
    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex items-center justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <span className="text-indigo-500">✦</span> Gemini Mutabakat Uzmanı
          </h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Plan-then-execute agent: önce analiz planı çıkarır, sonra tool'larla her adımı çalıştırır.
          </p>
        </div>
        <button
          onClick={run}
          className="shrink-0 px-3 py-1.5 bg-indigo-600 text-white text-xs font-medium rounded-md hover:bg-indigo-700"
        >
          Detaylı Analiz Başlat
        </button>
      </div>
    );
  }

  const { plan, steps } = data ? buildSteps(data.trace) : { plan: undefined, steps: [] };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <span className="text-indigo-500">✦</span> Gemini Mutabakat Uzmanı
        </h3>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-xs text-gray-400">{data.iterations} tur · {steps.length} adım</span>
          )}
          <button
            onClick={() => { setOpen(false); setData(null); }}
            className="text-xs text-gray-500 hover:text-gray-700 underline"
          >
            Kapat
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-gray-500 py-6">
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Agent planı çıkarıyor ve tool'ları çağırıyor… (15-30 sn)
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-100 rounded-lg p-4 text-sm">
          <div className="font-semibold text-red-700 mb-1">⚠ {error.message}</div>
          {error.upstream && (
            <div className="mt-2">
              <div className="text-xs text-red-600 font-medium mb-1">Gemini ham hatası:</div>
              <pre className="text-[11px] bg-white border border-red-100 rounded p-2 overflow-x-auto text-red-800 whitespace-pre-wrap break-words">
                {error.upstream}
              </pre>
            </div>
          )}
          <button
            onClick={run}
            className="mt-3 text-xs px-3 py-1.5 bg-red-600 text-white rounded-md hover:bg-red-700"
          >
            Yeniden Dene
          </button>
        </div>
      )}

      {data && !loading && (
        <>
          {plan && (
            <div className="mb-4 bg-indigo-50 border border-indigo-100 rounded-lg p-3">
              <div className="text-xs font-semibold text-indigo-700 mb-1">📝 Analiz Planı</div>
              <div className="text-xs text-gray-700 whitespace-pre-wrap">{plan}</div>
            </div>
          )}

          {steps.length > 0 && (
            <ol className="space-y-3 mb-4">
              {steps.map((s) => (
                <li key={s.index} className="border-l-2 border-indigo-200 pl-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold text-indigo-700">{s.index}.</span>
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-indigo-50 text-indigo-700">
                      {TOOL_LABEL[s.toolName] ?? s.toolName}
                    </span>
                    {Object.keys(s.args).length > 0 && (
                      <span className="text-[10px] font-mono text-gray-500">
                        ({Object.entries(s.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-600 font-mono pl-2">
                    → {summarizeResult(s.result)}
                  </div>
                  {s.note && (
                    <div className="mt-1 text-xs text-gray-600 italic pl-2">{s.note}</div>
                  )}
                </li>
              ))}
            </ol>
          )}

          {data.summary && (
            <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-3">
              <div className="text-xs font-semibold text-emerald-700 mb-1">🎯 Özet ve Aksiyon</div>
              <div className="text-sm text-gray-700 whitespace-pre-wrap">{data.summary}</div>
            </div>
          )}

          <div className="mt-3 flex justify-end">
            <button
              onClick={run}
              className="text-xs px-3 py-1.5 border border-gray-200 rounded-md text-gray-600 hover:bg-gray-50"
            >
              Yeniden Çalıştır
            </button>
          </div>
        </>
      )}
    </div>
  );
}
