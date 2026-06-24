"use client";
import { useRouter } from "next/navigation";

export function YearSelect({ years, value }: { years: number[]; value: number }) {
  const router = useRouter();
  return (
    <select
      value={value}
      onChange={(e) => router.push(Number(e.target.value) === years[0] ? "/" : `/?year=${e.target.value}`)}
      className="rounded-full border border-line bg-surface-2 px-3 py-1 text-sm text-ink"
      aria-label="選擇球季年份"
    >
      {years.map((y) => (
        <option key={y} value={y}>{y} 球季</option>
      ))}
    </select>
  );
}
