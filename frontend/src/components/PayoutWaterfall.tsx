"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Cell,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { WaterfallLine } from "@/src/lib/api";

const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });

const TYPE_LABEL: Record<string, string> = {
  revenue:          "Satış Geliri",
  commission:       "Komisyon",
  campaign:         "Kampanya Kesintisi",
  shipping_support: "Kargo Desteği",
  return_refund:    "İade Geri Ödemesi",
  stopaj:           "Stopaj",
  adjustment:       "Düzeltme",
  other:            "Diğer",
};

interface Step {
  description: string;
  amount: number;
  cumulative: number;
  base: number;
  size: number;
  line_type: string;
  explanation: string;
  is_anomalous: boolean;
  index: number;
}

function buildSteps(lines: WaterfallLine[]): { steps: Step[]; total: number } {
  let cumulative = 0;
  const steps: Step[] = lines.map((l, i) => {
    const base = l.amount >= 0 ? cumulative : cumulative + l.amount;
    const size = Math.abs(l.amount);
    cumulative += l.amount;
    return {
      description: l.description,
      amount: l.amount,
      cumulative,
      base,
      size,
      line_type: l.line_type,
      explanation: l.explanation,
      is_anomalous: l.is_anomalous,
      index: i,
    };
  });
  return { steps, total: cumulative };
}

function colorFor(step: Step) {
  if (step.is_anomalous) return "#ef4444"; // red
  if (step.amount >= 0) return "#10b981";  // emerald
  return "#94a3b8";                          // slate
}

export default function PayoutWaterfall({ lines }: { lines: WaterfallLine[] }) {
  if (!lines || lines.length === 0) return null;
  const { steps, total } = buildSteps(lines);

  const chartData = steps.map((s) => ({
    label: TYPE_LABEL[s.line_type] ?? s.description,
    base: s.base,
    size: s.size,
    step: s,
  }));

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">Payout Waterfall</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Gemini her kalemi sınıflandırdı; anomali bayrağı kırmızı renkte gösterilir.
          </p>
        </div>
        <span className="text-xs font-mono text-gray-700 px-2 py-1 bg-gray-50 rounded-md">
          Net: {TRY.format(total)}
        </span>
      </div>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 10, right: 10, bottom: 40, left: 0 }}>
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: "#64748b" }}
              interval={0}
              angle={-30}
              textAnchor="end"
              height={70}
            />
            <YAxis tick={{ fontSize: 11, fill: "#64748b" }} tickFormatter={(v) => TRY.format(v as number)} />
            <Tooltip
              cursor={{ fill: "rgba(99, 102, 241, 0.06)" }}
              content={({ active, payload }) => {
                if (!active || !payload || !payload[0]) return null;
                const step: Step = payload[0].payload.step;
                return (
                  <div className="bg-white shadow-lg rounded-lg border border-gray-100 p-3 text-xs max-w-xs">
                    <div className="font-semibold text-gray-800 mb-1">{step.description}</div>
                    <div className={`font-mono ${step.amount < 0 ? "text-red-600" : "text-emerald-700"}`}>
                      {step.amount >= 0 ? "+" : ""}{TRY.format(step.amount)}
                    </div>
                    <div className="text-gray-500 mt-1">Kümülatif: {TRY.format(step.cumulative)}</div>
                    {step.explanation && (
                      <p className="text-gray-600 mt-2 italic">"{step.explanation}"</p>
                    )}
                    {step.is_anomalous && (
                      <div className="mt-2 text-red-600 font-medium">⚠ Anomali işareti</div>
                    )}
                  </div>
                );
              }}
            />
            <ReferenceLine y={0} stroke="#94a3b8" />
            <Bar dataKey="base" stackId="wf" fill="transparent" />
            <Bar dataKey="size" stackId="wf" radius={[4, 4, 0, 0]}>
              {chartData.map((d, i) => (
                <Cell key={i} fill={colorFor(d.step)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Anomalous line callouts */}
      {steps.some((s) => s.is_anomalous) && (
        <div className="mt-4 space-y-2">
          {steps.filter((s) => s.is_anomalous).map((s) => (
            <div key={s.index} className="bg-red-50 border border-red-100 rounded-lg p-3 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-medium text-red-700">⚠ {s.description}</span>
                <span className="font-mono text-red-700">{TRY.format(s.amount)}</span>
              </div>
              {s.explanation && (
                <p className="text-red-700/80 mt-1 italic">"{s.explanation}"</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
