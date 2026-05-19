interface MetricCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon?: React.ReactNode;
}

export default function MetricCard({ title, value, subtitle, icon }: MetricCardProps) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 border-l-4 border-l-indigo-500 p-5 flex items-start gap-4">
      {icon && (
        <div className="text-indigo-500 mt-0.5 shrink-0">{icon}</div>
      )}
      <div className="min-w-0">
        <p className="text-sm text-gray-500 font-medium truncate">{title}</p>
        <p className="text-2xl font-bold text-gray-800 mt-0.5 truncate">{value}</p>
        {subtitle && (
          <p className="text-xs text-gray-400 mt-1 truncate">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
