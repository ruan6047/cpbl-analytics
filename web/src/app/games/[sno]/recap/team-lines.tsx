"use client";

// recap ④兩隊表現行：**吸收既有雛形，不重寫**——本場焦點／特殊紀錄／賽事資訊沿用
// `game-live-page.tsx` 原本的產生器（已抽到 `game-summary.ts`），只換容器。
//
// 焦點區的球迷用語（魯閣／中計／煮粥…）**維持現況**：brief 的非目標明訂「球迷暱稱於
// recap **正式文案**」，焦點區既有用法不在此限；結論行事實句才是正式文案。

import { Card, Eyebrow, TeamLogo } from "@/components/ui";
import type { Highlight } from "../game-summary";

// #218 身分標籤：隊色只在印記，不鋪底；帶隊的焦點前置該隊印記。
function Chip({ text, team }: Highlight) {
  return (
    <span className="pm-tag inline-flex items-center gap-1.5 !text-ink">
      {team && <TeamLogo code={team} size={14} decorative />}{text}
    </span>
  );
}

export function TeamLines({ highlights, milestones, info }: {
  highlights: Highlight[];
  milestones: Highlight[];
  info: [string, React.ReactNode][];
}) {
  if (!highlights.length && !milestones.length && !info.length) return null;
  return (
    <Card className="flex min-w-0 flex-col gap-4">
      {highlights.length > 0 && (
        <section>
          <Eyebrow className="mb-2">本場焦點</Eyebrow>
          <div className="flex flex-wrap gap-1.5">
            {highlights.map((h, i) => <Chip key={i} {...h} />)}
          </div>
        </section>
      )}
      {milestones.length > 0 && (
        <section>
          <Eyebrow className="mb-2">特殊紀錄</Eyebrow>
          <div className="flex flex-wrap gap-1.5">
            {milestones.map((m, i) => <Chip key={i} {...m} />)}
          </div>
        </section>
      )}
      {info.length > 0 && (
        <dl className="space-y-1.5 border-t border-line pt-3.5 text-sm">
          {info.map(([label, value]) => (
            <div key={label} className="flex gap-3">
              <dt className="w-10 shrink-0 text-muted">{label}</dt>
              <dd className="min-w-0 text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}
