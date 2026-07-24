"use client";

import { useState } from "react";
import { ContextSwitcher } from "@/components/hierarchical-tabs";
import { StatTile } from "@/components/ui";
import type { TeamSplitScope } from "@/lib/api";

// client 端純格式化（與 parts.tsx f2/f3 一致；避免把 server 模組圖拉進 client bundle）。
const f3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0\./, "."));
const f2 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
const runDiff = (v: number | null | undefined) => (v == null ? "—" : v > 0 ? `+${v}` : `${v}`);

type ScopeKey = "full" | "first" | "second";
type MetricKey = "ops" | "era" | "whip" | "rs_pg" | "ra_pg" | "run_diff";

/**
 * 攻守概覽的全年／上半季／下半季範圍切換（UX-TEAM-SPLIT-SCOPE1）。
 *
 * 三範圍走**同一** gamelog+games 聚合路徑（後端 /api/v1/season/team-split，禁混用 team_current）；
 * 切換僅影響本區塊。名次（rankOf）依所選範圍在**同範圍** 6 隊內比，不跨範圍。半季無完成場（如季初
 * 下半季）→ 該選項退化不可選，不顯示誤導的空/零值；小樣本半季照常顯示並標示樣本量（需求方定案）。
 * DER 無半季粒度、非口徑四指標，切半季時固定「全年」值並去名次，避免與半季指標混淆誤導。
 *
 * 範圍軸在此為**本區塊的情境過濾**（同 6 格結構、僅換資料集、無季後賽結構性換表），依設計系統
 * §4.3「換資料集、表結構同」判準採 `ContextSwitcher`（膠囊 switch），而非 /standings 頁級主分頁 tablist。
 */
export function TeamScopeOverview({ teamCode, scopes, der, teamN }: {
  teamCode: string;
  scopes: TeamSplitScope[];
  der?: { value: string; rank: number | null } | null;
  teamN: number;
}) {
  // 僅提供有完成場的範圍（未就緒半季退化為不可選）；全年恆在。
  const usable = scopes.filter((s) => s.available || s.key === "full");
  const [active, setActive] = useState<ScopeKey>("full");
  const scope = usable.find((s) => s.key === active) ?? usable[0];
  const teams = scope.teams;
  const mine = teams.find((t) => t.code === teamCode);

  // 名次：所選範圍內 6 隊排序（前段班綠、後段班紅，由 StatTile 依 rankTotal 判定）。
  const rankOf = (key: MetricKey, lowerBetter: boolean): number | null => {
    const v = mine?.[key];
    if (v == null) return null;
    const vals = teams.map((t) => t[key]).filter((x): x is number => x != null);
    const sorted = [...vals].sort((a, b) => (lowerBetter ? a - b : b - a));
    const r = sorted.indexOf(v);
    return r >= 0 ? r + 1 : null;
  };

  const g = mine?.g ?? 0;
  const isHalf = scope.key !== "full";
  const smallSample = isHalf && g > 0 && g < 25;

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        {usable.length > 1 && (
          <ContextSwitcher
            label="範圍"
            values={usable.map((s) => s.key)}
            value={scope.key}
            render={(k) => usable.find((s) => s.key === k)?.label ?? k}
            onChange={setActive}
          />
        )}
        {/* 樣本量標示：小樣本半季照常顯示但標記，避免誤導（需求方定案）。 */}
        <span className="text-[11px] tabular-nums text-muted">
          {g > 0 ? `${g} 場` : "尚無完成場"}
          {smallSample && <span className="ml-1 text-faint">· 樣本偏小</span>}
        </span>
      </div>
      <div className="grid gap-x-6 gap-y-3 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted">進攻</h3>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <StatTile label="OPS" value={f3(mine?.ops)} accent rank={rankOf("ops", false)} rankTotal={teamN} />
            <StatTile label="得分/場" value={f2(mine?.rs_pg)} rank={rankOf("rs_pg", false)} rankTotal={teamN} />
            <StatTile label="得失分差" value={runDiff(mine?.run_diff)} accent rank={rankOf("run_diff", false)} rankTotal={teamN} />
          </div>
        </div>
        <div>
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted">守備投球</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatTile label="ERA" value={f2(mine?.era)} rank={rankOf("era", true)} rankTotal={teamN} />
            <StatTile label="WHIP" value={f2(mine?.whip)} rank={rankOf("whip", true)} rankTotal={teamN} />
            <StatTile label="失分/場" value={f2(mine?.ra_pg)} rank={rankOf("ra_pg", true)} rankTotal={teamN} />
            {/* DER 無半季粒度：切半季固定全年值、去名次並標「全年」以免誤導。 */}
            <StatTile label={isHalf ? "DER · 全年" : "DER"} value={der?.value ?? "—"}
              rank={isHalf ? null : (der?.rank ?? null)} rankTotal={teamN} />
          </div>
        </div>
      </div>
    </section>
  );
}
