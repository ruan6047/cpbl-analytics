"use client";
import { useRouter } from "next/navigation";

export function YearSelect({ years, value, kind = "A" }: { years: number[]; value: number; kind?: string }) {
  const router = useRouter();
  const kindQ = kind === "D" ? "kind=D" : "";
  return (
    <select
      value={value}
      onChange={(e) => {
        const y = Number(e.target.value);
        const yearQ = y === years[0] ? "" : `year=${e.target.value}`;
        const qs = [kindQ, yearQ].filter(Boolean).join("&");
        router.push(qs ? `/?${qs}` : "/");
      }}
      className="rounded-full border border-line bg-surface-2 px-3 py-1 text-sm text-ink"
      aria-label="選擇球季年份"
    >
      {years.map((y) => (
        <option key={y} value={y}>{y} 球季</option>
      ))}
    </select>
  );
}
