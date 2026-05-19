"use client";

import { useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface DayPoint {
  date: string;
  gross: number;
  net: number;
}

const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });

function formatDay(dateStr: string) {
  const d = new Date(dateStr);
  return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "short" });
}

export default function SalesChart() {
  const [data, setData] = useState<DayPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/dashboard/chart")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((raw: DayPoint[]) =>
        setData(raw.map((d) => ({ ...d, date: formatDay(d.date) })))
      )
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="h-48 bg-gray-100 rounded-xl animate-pulse" />;
  }

  if (error || data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm bg-white rounded-xl border border-gray-100">
        {error ? `Grafik yüklenemedi: ${error}` : "Grafik verisi yok"}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
      <h2 className="text-base font-semibold text-gray-700 mb-4">Son 7 Gün — Brüt / Net Satış</h2>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="grossGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="netGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
          <YAxis
            tick={{ fontSize: 11, fill: "#9ca3af" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `₺${(v / 1000).toFixed(0)}K`}
            width={48}
          />
          <Tooltip
            formatter={(value: number, name: string) => [
              TRY.format(value),
              name === "gross" ? "Brüt Satış" : "Net Hak Ediş",
            ]}
            labelStyle={{ color: "#374151", fontWeight: 600 }}
            contentStyle={{ border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }}
          />
          <Legend
            formatter={(value) => (value === "gross" ? "Brüt Satış" : "Net Hak Ediş")}
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12 }}
          />
          <Area type="monotone" dataKey="gross" stroke="#6366f1" strokeWidth={2} fill="url(#grossGrad)" dot={false} />
          <Area type="monotone" dataKey="net" stroke="#10b981" strokeWidth={2} fill="url(#netGrad)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
