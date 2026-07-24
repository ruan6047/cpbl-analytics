"use client";

import { useRouter } from "next/navigation";
import { MainTabs } from "@/components/hierarchical-tabs";
import { LevelYearNav } from "@/components/level-year-nav";
import { NavBarRow, StickyNavBar } from "@/components/sticky-nav-bar";

// 戰績頁一體式導覽欄（§4.3 A2 定案）：賽季階段 seg＝主分頁（單層 tablist），
// kind（一/二軍）＋year＝右側情境 controls（共用 LevelYearNav）。
// seg 項目由 server 端 segsFor(kind) 傳入（二軍無上下半季）；切層級/年份時保留 seg，
// 由 server 端 fallback 邏輯處理失效 seg（退回全年）。
export function StandingsNav({ kind, years, selectedYear, seg, segs }: {
  kind: string; years: number[]; selectedYear: number; seg: number;
  segs: { v: number; label: string }[];
}) {
  const router = useRouter();
  const pushSeg = (v: string) => {
    const p = new URLSearchParams();
    if (kind === "D") p.set("kind", "D");
    if (selectedYear !== years[0]) p.set("year", String(selectedYear));
    if (v !== "0") p.set("seg", v);
    const qs = p.toString();
    router.push(qs ? `/standings?${qs}` : "/standings");
  };
  return (
    <StickyNavBar label="戰績導覽" flush>
      <NavBarRow
        align="end"
        main={
          <div className="flex min-w-0 items-center overflow-x-auto overscroll-x-contain">
            <MainTabs label="賽季階段" value={String(seg)} onChange={pushSeg}
              items={segs.map((s) => ({ value: String(s.v), label: s.label }))} />
          </div>
        }
        controls={
          <LevelYearNav kind={kind} years={years} selectedYear={selectedYear} base="/standings"
            params={{ seg: seg ? String(seg) : undefined }} />
        }
      />
    </StickyNavBar>
  );
}
