"use client";

import { useState, type ReactNode } from "react";
import { ContextSwitcher, MainTabs, TabPanel, mainTabId } from "@/components/hierarchical-tabs";
import { StickyNavBar } from "@/components/sticky-nav-bar";
import { YearSelect } from "@/components/year-select";
import { TeamScopeOverview } from "./scope-overview";
import type { TeamSplitScope } from "@/lib/api";

type ScopeKey = "full" | "first" | "second";
const HALF_LABEL: Record<string, string> = { full: "全年", first: "上半季", second: "下半季" };

// content=null 保留給賽季佔位（value=SEASON_GROUP）：其內容由 TeamTabs 自行組裝。
export type TeamGroup = { value: string; label: string; content: ReactNode | null };

/**
 * 球隊頁一體式導覽（UX-TEAM-SPLIT-SCOPE1；比照球員頁 PlayerNavigation 的 §4.3 canonical）。
 *
 * 頂層群組順序由 page.tsx 的 `groups` 決定（現為 近日焦點／賽季／現役陣容／歷屆成員／隊史，
 * **落地預設＝第一個群組「近日焦點」**）。群組各自換一份內容＝一級頁籤帶（`MainTabs`）＋同色 `TabPanel`。
 * value="season" 的佔位群組由本元件接手渲染：面板頂端是範圍列——半季 全年/上半季/下半季
 * （#218「範圍用分段切換，不用多層頁籤」＝`ContextSwitcher`，client 即時切換，驅動攻守概覽）＋年度
 * YearSelect（URL `?year=`；當季在 years[0] 故當季無參數）。切年度→server 重抓該年
 * 全部賽季區塊資料並 remount。半季只影響攻守概覽；主力選手/對戰/戰績分項隨年度不隨半季
 * （官方個人與特殊戰績無上下半季，見卡片決策）。
 */
export const SEASON_GROUP = "season";
const TEAM_PANEL = "team-panel";

export function TeamTabs({ code, teamN, scopes, der, seasonSupporting, groups, year, years, landOnSeason }: {
  code: string;
  teamN: number;
  scopes: TeamSplitScope[];
  der?: { value: string; rank: number | null } | null;
  seasonSupporting: ReactNode;
  groups: TeamGroup[];
  year: number;
  years: number[];
  /** 帶 `?year=` 進站（含切年度導頁）時直接落在賽季，否則落地預設＝第一個群組（近日焦點）。 */
  landOnSeason?: boolean;
}) {
  const [activeGroup, setActiveGroup] = useState<string>(
    landOnSeason && groups.some((g) => g.value === SEASON_GROUP) ? SEASON_GROUP : (groups[0]?.value ?? SEASON_GROUP));
  const [activeHalf, setActiveHalf] = useState<ScopeKey>("full");

  // 半季範圍：僅有完成場的半季可選（未就緒半季退化）；只剩全年則不顯示切換。
  const halves = scopes.filter((s) => s.available || s.key === "full");
  const halfKeys = halves.length > 1 ? halves.map((s) => s.key as ScopeKey) : [];
  const activeScope = scopes.find((s) => s.key === activeHalf)
    ?? scopes.find((s) => s.key === "full") ?? scopes[0];

  // 群組順序完全依 page.tsx 傳入；賽季佔位（value=SEASON_GROUP）由本元件掛上範圍列與內容。
  const contentFor = Object.fromEntries(groups.map((g) => [g.value, g.content]));
  const isHalf = activeHalf !== "full";
  const showYear = years.length > 1;

  return (
    <div>
      <StickyNavBar label="球隊資料導覽" flush>
        <MainTabs label="球隊資料範圍" panelId={TEAM_PANEL}
          items={groups.map((g) => ({ value: g.value, label: g.label }))}
          value={activeGroup} onChange={setActiveGroup} />
      </StickyNavBar>

      <TabPanel id={TEAM_PANEL} labelledBy={mainTabId(TEAM_PANEL, activeGroup)}>
      {activeGroup === SEASON_GROUP ? (
        <div className="space-y-5">
          {(halfKeys.length > 0 || showYear) && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {halfKeys.length > 0 && (
                <ContextSwitcher label="範圍" values={halfKeys} value={activeHalf}
                  render={(v) => HALF_LABEL[v] ?? v} onChange={setActiveHalf} />
              )}
              {showYear && (
                <div className="ml-auto">
                  <YearSelect years={years} value={year} basePath={`/teams/${code}`} />
                </div>
              )}
            </div>
          )}
          {activeScope && (
            <TeamScopeOverview teamCode={code} scope={activeScope} teamN={teamN} der={der} half={activeHalf} />
          )}
          {isHalf && (
            <p className="-mt-3 text-[11px] text-faint">
              主力選手／對戰各隊／戰績分項為全年（官方個人與特殊戰績無上下半季）。
            </p>
          )}
          {seasonSupporting}
        </div>
      ) : (
        contentFor[activeGroup]
      )}
      </TabPanel>
    </div>
  );
}
