import Link from "next/link";
import { YearSelect } from "@/components/year-select";

const LEVELS = [{ v: "A", label: "一軍" }, { v: "D", label: "二軍" }];

// 一軍/二軍 + 年份選擇器：全站 kind＋year 基底軸的共用件（§4.3；戰績/排行/賽況共用）。
// 輸出裸 controls（置於導覽欄 controls 插槽）；層級走路由切換語彙（Link + aria-current，§4.1）。
// params：切換層級/年份時要一併保留的頁面主軸參數（如 seg/view）；年份清單隨 kind 不同，切層級時重置年份。
export function LevelYearNav({ kind, years, selectedYear, base, params }: {
  kind: string; years: number[]; selectedYear: number; base: string;
  params?: Record<string, string | undefined>;
}) {
  const hrefFor = (lv: string) => {
    const p = new URLSearchParams();
    if (lv === "D") p.set("kind", "D");
    for (const [k, v] of Object.entries(params ?? {})) if (v) p.set(k, v);
    const qs = p.toString();
    return qs ? `${base}?${qs}` : base;
  };
  return (
    <>
      <span role="group" aria-label="層級" className="flex items-center gap-1">
        {LEVELS.map((lv) => {
          const active = (lv.v === "D") === (kind === "D");
          return (
            <Link key={lv.v} href={hrefFor(lv.v)} aria-current={active ? "page" : undefined}
              className={`inline-flex min-h-11 touch-manipulation items-center rounded-full px-3 text-sm font-medium transition ${
                active ? "bg-ink text-paper" : "bg-surface-2 text-muted hover:text-ink"}`}>
              {lv.label}
            </Link>
          );
        })}
      </span>
      <span className="h-4 w-px bg-line" aria-hidden />
      <YearSelect years={years} value={selectedYear} kind={kind} basePath={base} params={params} />
    </>
  );
}
