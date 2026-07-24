"use client";

import { useState, type ReactNode } from "react";
import { HierarchicalTabs, type HierarchicalTabGroup } from "@/components/hierarchical-tabs";
import { StickyNavBar } from "@/components/sticky-nav-bar";
import { YearSelect } from "@/components/year-select";
import { TeamScopeOverview } from "./scope-overview";
import type { TeamSplitScope } from "@/lib/api";

type ScopeKey = "full" | "first" | "second";
const HALF_LABEL: Record<string, string> = { full: "全年", first: "上半季", second: "下半季" };

export type TeamGroup = { value: string; label: string; content: ReactNode };

/**
 * 球隊頁一體式導覽（UX-TEAM-SPLIT-SCOPE1；比照球員頁 PlayerNavigation 的 §4.3 canonical）。
 *
 * 頂層群組＝賽季／近日焦點／現役陣容／歷史球員／隊史（HierarchicalTabs）；「賽季」展開子頁籤
 * 全年/上半季/下半季（半季軸，client 即時切換，驅動攻守概覽）。年度軸＝controls 的 YearSelect
 * （URL `?year=`，僅賽季顯示；當季在 years[0] 故當季無參數）。切年度→server 重抓該年全部賽季區塊
 * 資料並 remount（回賽季/全年）。半季只影響攻守概覽；主力選手/對戰/戰績分項隨年度不隨半季
 * （官方個人與特殊戰績無上下半季，見卡片決策）。
 */
export function TeamTabs({ code, teamN, scopes, der, seasonSupporting, groups, year, years }: {
  code: string;
  teamN: number;
  scopes: TeamSplitScope[];
  der?: { value: string; rank: number | null } | null;
  seasonSupporting: ReactNode;
  groups: TeamGroup[];
  year: number;
  years: number[];
}) {
  const [activeGroup, setActiveGroup] = useState<string>("season");
  const [activeHalf, setActiveHalf] = useState<ScopeKey>("full");

  // 賽季子頁籤：僅有完成場的半季可選（未就緒半季退化）；只剩全年則不顯示子頁籤托盤。
  const halves = scopes.filter((s) => s.available || s.key === "full");
  const seasonItems = halves.length > 1
    ? halves.map((s) => ({ value: s.key, label: HALF_LABEL[s.key] ?? s.label }))
    : [];
  const activeScope = scopes.find((s) => s.key === activeHalf)
    ?? scopes.find((s) => s.key === "full") ?? scopes[0];

  const tabGroups: HierarchicalTabGroup<string, string>[] = [
    { value: "season", label: "賽季", items: seasonItems },
    ...groups.map((g) => ({ value: g.value, label: g.label, items: [] as { value: string; label: string }[] })),
  ];
  const contentFor = Object.fromEntries(groups.map((g) => [g.value, g.content]));
  const isHalf = activeHalf !== "full";

  return (
    <div className="space-y-5">
      <StickyNavBar label="球隊資料導覽" flush>
        <HierarchicalTabs
          label="球隊資料範圍"
          groups={tabGroups}
          activeGroup={activeGroup}
          activeItem={activeHalf}
          onGroupChange={setActiveGroup}
          onItemChange={(v) => setActiveHalf(v as ScopeKey)}
          controls={activeGroup === "season" && years.length > 1
            ? <YearSelect years={years} value={year} basePath={`/teams/${code}`} />
            : undefined}
        />
      </StickyNavBar>

      {activeGroup === "season" ? (
        <div className="space-y-5">
          {activeScope && (
            <TeamScopeOverview teamCode={code} scope={activeScope} teamN={teamN} der={der} half={activeHalf} />
          )}
          {isHalf && (
            <p className="-mt-2 text-[11px] text-faint">
              主力選手／對戰各隊／戰績分項為全年（官方個人與特殊戰績無上下半季）。
            </p>
          )}
          {seasonSupporting}
        </div>
      ) : (
        contentFor[activeGroup]
      )}
    </div>
  );
}
