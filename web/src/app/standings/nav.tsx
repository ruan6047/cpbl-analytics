"use client";

import { useRouter } from "next/navigation";
import { type ReactNode } from "react";
import { MainTabs, TabPanel, mainTabId } from "@/components/hierarchical-tabs";
import { LevelYearNav } from "@/components/level-year-nav";
import { NavBarRow, StickyNavBar } from "@/components/sticky-nav-bar";

// 戰績頁一體式導覽欄（§4.3 A2 定案）：賽季階段 seg＝主分頁（單層 tablist），
// kind（一/二軍）＋year＝右側情境 controls（共用 LevelYearNav）。
// seg 項目由 server 端 segsFor(kind) 傳入（二軍無上下半季）；切層級/年份時保留 seg，
// 由 server 端 fallback 邏輯處理失效 seg（退回全年）。
// 頁面內容以 children 傳入，接在頁籤帶下的同色 TabPanel（#218 頁籤＋面板）。
const STANDINGS_PANEL = "standings-panel";

export function StandingsNav({ kind, years, selectedYear, seg, segs, children }: {
  kind: string; years: number[]; selectedYear: number; seg: number;
  segs: { v: number; label: string }[];
  children: ReactNode;
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
    <>
    <StickyNavBar label="戰績導覽" flush>
      <NavBarRow
        align="end"
        main={
          <MainTabs label="賽季階段" value={String(seg)} onChange={pushSeg} panelId={STANDINGS_PANEL}
            items={segs.map((s) => ({ value: String(s.v), label: s.label }))} />
        }
        controls={
          <LevelYearNav kind={kind} years={years} selectedYear={selectedYear} base="/standings"
            params={{ seg: seg ? String(seg) : undefined }} />
        }
      />
    </StickyNavBar>
    <TabPanel id={STANDINGS_PANEL} labelledBy={mainTabId(STANDINGS_PANEL, String(seg))}>{children}</TabPanel>
    </>
  );
}
