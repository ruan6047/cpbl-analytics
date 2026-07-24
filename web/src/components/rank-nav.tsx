"use client";

import { useRouter } from "next/navigation";
import { HierarchicalTabs } from "@/components/hierarchical-tabs";
import { LevelYearNav } from "@/components/level-year-nav";
import { StickyNavBar } from "@/components/sticky-nav-bar";

// 排行中心一體式導覽欄（§4.3 第二例；取代 RankRoleTabs＋獨立 LevelYearNav 兩列）：
// role（打者/投手）＝group（跨路由 /batters↔/pitchers，保留 kind/year/view 脈絡）、
// view（完整清單/獎項排行榜）＝item 主內容視圖（?view= 分頁，取代垂直堆疊）、
// kind＋year＝右側情境 controls（共用 LevelYearNav）。
export type RankView = "list" | "awards";

const VIEW_ITEMS = [
  { value: "list", label: "完整清單" },
  { value: "awards", label: "獎項排行榜" },
] as const;

const GROUPS = [
  { value: "batting", label: "打者", items: VIEW_ITEMS },
  { value: "pitching", label: "投手", items: VIEW_ITEMS },
] as const;

const BASE: Record<string, string> = { batting: "/batters", pitching: "/pitchers" };

/** URL 形狀保持 canonical：預設值（kind=A、預設年、view=list）不寫進網址。 */
function hrefFor(role: string, view: RankView, kind: string, year: number, defaultYear: number) {
  const p = new URLSearchParams();
  if (kind === "D") p.set("kind", "D");
  if (year !== defaultYear) p.set("year", String(year));
  if (view !== "list") p.set("view", view);
  const qs = p.toString();
  return qs ? `${BASE[role]}?${qs}` : BASE[role];
}

export function RankNav({ role, view, kind, years, selectedYear }: {
  role: "batting" | "pitching"; view: RankView; kind: string;
  years: number[]; selectedYear: number;
}) {
  const router = useRouter();
  const push = (nextRole: string, nextView: RankView) =>
    router.push(hrefFor(nextRole, nextView, kind, selectedYear, years[0]));
  return (
    <StickyNavBar label="排行導覽">
      <HierarchicalTabs label="排行範圍" groups={GROUPS}
        activeGroup={role} activeItem={view}
        onGroupChange={(nextRole) => push(nextRole, view)}
        onItemChange={(nextView) => push(role, nextView)}
        controls={
          <LevelYearNav kind={kind} years={years} selectedYear={selectedYear} base={BASE[role]}
            params={{ view: view === "list" ? undefined : view }} />
        } />
    </StickyNavBar>
  );
}
