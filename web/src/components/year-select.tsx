"use client";
import { useRouter } from "next/navigation";

// 年份原生 select（§4.2 選擇族；圓角統一 control `rounded-lg`，conformance H8）。
// params：切換年份時要一併保留的頁面主軸參數（如 standings 的 seg、排行的 view）。
export function YearSelect({ years, value, kind = "A", basePath = "/", params }: {
  years: number[]; value: number; kind?: string; basePath?: string;
  params?: Record<string, string | undefined>;
}) {
  const router = useRouter();
  return (
    <select
      value={value}
      onChange={(e) => {
        const y = Number(e.target.value);
        const p = new URLSearchParams();
        if (kind === "D") p.set("kind", "D");
        if (y !== years[0]) p.set("year", e.target.value);
        for (const [k, v] of Object.entries(params ?? {})) if (v) p.set(k, v);
        const qs = p.toString();
        router.push(qs ? `${basePath}?${qs}` : basePath);
      }}
      className="min-h-11 rounded-lg border border-line bg-surface-2 px-3 py-1 text-sm text-ink focus:border-ink"
      aria-label="選擇球季年份"
    >
      {years.map((y) => (
        <option key={y} value={y}>{y} 球季</option>
      ))}
    </select>
  );
}
