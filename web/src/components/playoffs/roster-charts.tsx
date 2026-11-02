"use client";

import { AbilityCard } from "@/components/ability-card";
import { SeasonTrendCard } from "@/app/players/[id]/trend";
import { DRAWER_COPY, pickAbility, type RosterPlayerDetail } from "@/lib/playoffs-roster";
import { teamColor } from "@/lib/teams";

// #415：名單抽屜的圖表模組（能力雷達＋本季走勢）。由 `roster-drawer.tsx` 以 `next/dynamic(ssr:false)` 按需載入，
// 讓 `/playoffs` 首載不帶 recharts 及其相依（改前 6 個 recharts chunk 合計約 121 kB gzip、占首載 41%）；
// 抽屜殼、標頭個人數值、載入／錯誤／過期文字態仍在首載即時渲染。
// 這裡只搬移 DrawerBody ready 態的兩段，圖表行為與資料契約不變（AbilityCard／SeasonTrendCard 原樣引用）。

export default function RosterCharts({ detail }: { detail: RosterPlayerDetail }) {
  const ab = pickAbility(detail);
  return (
    <>
      <section aria-label={ab?.label ?? DRAWER_COPY.abilitySeason} className="space-y-2">
        <h3 className="text-sm font-bold text-muted">{ab?.label ?? DRAWER_COPY.abilitySeason}</h3>
        {ab ? <AbilityCard card={ab.card} color={teamColor(detail.team_code)} compact />
          : <p className="text-sm text-muted">{DRAWER_COPY.abilityNone}</p>}
      </section>
      {detail.trend ? (
        // 包一層：SeasonTrendCard 的 Card 是 h-full，直接放在捲動區會被撐成整個抽屜高。
        <div><SeasonTrendCard trend={detail.trend.items} role={detail.player.role} isRetired={false} /></div>
      ) : null}
    </>
  );
}
