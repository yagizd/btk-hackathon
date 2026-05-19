"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/" },
  { label: "Siparişler", href: "/#orders" },
  { label: "Faturalar", href: "/faturalar" },
  { label: "Mutabakat", href: "/mutabakat" },
];

export default function Sidebar() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/" || href === "/#orders") return pathname === "/";
    return pathname === href;
  }

  return (
    <aside className="w-56 shrink-0 bg-white border-r border-gray-100 flex flex-col py-8 px-4 gap-1 shadow-sm">
      <div className="mb-6 px-2">
        <span className="text-lg font-bold text-indigo-600 tracking-tight">BTK Panel</span>
      </div>
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.label}
          href={item.href}
          className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            isActive(item.href)
              ? "bg-indigo-50 text-indigo-700"
              : "text-gray-600 hover:bg-indigo-50 hover:text-indigo-700"
          }`}
        >
          {item.label}
        </Link>
      ))}
    </aside>
  );
}
