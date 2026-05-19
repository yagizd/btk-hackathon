"use client";

import { useEffect, useState } from "react";
import { fetchDashboard, classifyAll, DashboardMetrics } from "@/src/lib/api";
import MetricCard from "@/src/components/MetricCard";
import OrdersTable from "@/src/components/OrdersTable";
import NLQueryBox from "@/src/components/NLQueryBox";
import Sidebar from "@/src/components/Sidebar";
import SalesChart from "@/src/components/SalesChart";
import UncertainReview from "@/src/components/UncertainReview";

const TRY = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });

export default function Home() {
  const [dashboard, setDashboard] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [classifying, setClassifying] = useState(true);

  useEffect(() => {
    // Önce tüm siparişleri classify et, sonra dashboard + tablo yükle
    setClassifying(true);
    classifyAll()
      .catch((e) => console.error("classify-all hatası:", e))
      .finally(() => {
        setClassifying(false);
        fetchDashboard()
          .then(setDashboard)
          .catch((e) => setError(e.message))
          .finally(() => setLoading(false));
      });
  }, []);

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans">
      <Sidebar />

      {/* Main content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-4">Dashboard</h1>

        {/* Classify banner */}
        {classifying && (
          <div className="flex items-center gap-2 mb-6 px-4 py-2.5 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-700 text-sm">
            <svg className="animate-spin h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Siparişler sınıflandırılıyor…
          </div>
        )}

        {/* Metric Cards */}
        {loading ? (
          <div className="grid grid-cols-2 gap-4 mb-8">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="mb-8 text-red-500 bg-red-50 rounded-lg p-4 text-sm">
            Dashboard yüklenemedi: {error}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 mb-8">
            <MetricCard
              title="Brüt Satış"
              value={dashboard ? TRY.format(dashboard.total_gross) : "—"}
              subtitle={`${dashboard?.order_count ?? 0} sipariş`}
            />
            <MetricCard
              title="Net Hak Ediş"
              value={dashboard ? TRY.format(dashboard.total_net) : "—"}
              subtitle="Komisyon sonrası net"
            />
            <MetricCard
              title="Komisyon"
              value={dashboard ? TRY.format(dashboard.total_commission) : "—"}
              subtitle="Pazaryeri kesintisi"
            />
            <MetricCard
              title="Belge Sayısı"
              value={dashboard ? String(dashboard.order_count) : "—"}
              subtitle={`${dashboard?.pending_classify ?? 0} sınıflandırma bekliyor`}
            />
          </div>
        )}

        {/* Sales Chart */}
        <section className="mb-8">
          <SalesChart />
        </section>

        {/* Orders Table */}
        <section id="orders" className="mb-8">
          <h2 className="text-lg font-semibold text-gray-700 mb-3">Siparişler</h2>
          <OrdersTable />
        </section>

        {/* Uncertain Review */}
        <section className="mb-8">
          <UncertainReview />
        </section>

        {/* NL Query */}
        <section>
          <NLQueryBox />
        </section>
      </main>
    </div>
  );
}
