import Link from "next/link";
import { YearSelect } from "@/components/year-select";

const LEVELS = [{ v: "A", label: "一軍" }, { v: "D", label: "二軍" }];

// 一軍/二軍 + 年份選擇器（戰績/球員榜/賽事頁共用）。base 為該頁路徑。
export function LevelYearNav({ kind, years, selectedYear, base }: { kind: string; years: number[]; selectedYear: number; base: string }) {
  return (
    <nav className="mb-4 flex flex-wrap items-center gap-2">
      {LEVELS.map((lv) => (
        <Link key={lv.v} href={lv.v === "A" ? base : `${base}?kind=D`}
          className={`rounded-full px-3 py-1 text-sm font-medium transition ${
            (lv.v === "D") === (kind === "D") ? "bg-ink text-paper" : "bg-surface-2 text-muted hover:bg-surface-2"}`}>
          {lv.label}
        </Link>
      ))}
      <span className="mx-1 h-4 w-px bg-line" />
      <YearSelect years={years} value={selectedYear} kind={kind} basePath={base} />
    </nav>
  );
}
