import type { ReactNode } from "react";
import { Card, EmptyState, PlayerLink } from "@/components/ui";
import type { TeamRecordsFranchise, TeamRecordsMilestone, TeamRecordsStreak, TeamUpcomingRecordsResponse } from "@/lib/api";

// 近日焦點・即將挑戰的紀錄（UX-TEAM-RECORDS1）。
//
// 2026-07-28 需求方人工審核後改版呈現形式，取代初版的三張 DataTable：「用表格反而
// 沒辦法了解各種近況」。三個具體失敗（見卡面「呈現形式」節）：(1) 目前/里程碑/還差
// 三格數字講同一件事，讀者要自己做算術；(2) 三張表三套欄位，掃過去要切三次心智
// 模型；(3) 空的子清單仍渲染標題與退化文案，形成誤導性留白。
//
// 改版原則：
//   - 每一筆讀起來是一句話，不是一列數字——三類共用同一個 <RecordRow>（同一套
//     排版節奏），差異只在文字內容，不做成三種元件。
//   - 「還差 N」（或連續安打的「連續 N 場」）是唯一的視覺錨點：字級最大、唯一上
//     accent 色；目前值／目標值退到左側描述行的次級文字（text-faint、字級最小）。
//   - 沒有內容的子分類**整段不渲染**（不留標題、不留退化文案）——需求方原話
//     「沒有數值的項目也可以隱藏起來避免資訊誤導」。三類全空時才顯示整區塊的
//     統一退化文案（既有行為，保留）。
//   - 生涯口徑／里程碑門檻／隊史逼近門檻與判準全部不變（本次純呈現層改版，
//     後端 `cpbl.api.team_records` 未改動）；隊史「本季貢獻非即時」的但書
//     移到該分類標題下方，分類隱藏時但書也一併不顯示（跟著它所屬的資料走）。

function RecordRow({ headline, detail, anchor }: { headline: ReactNode; detail?: ReactNode; anchor: ReactNode }) {
  return (
    <li className="flex items-center gap-3 py-2">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-ink">{headline}</div>
        {detail && <div className="truncate text-[11px] text-faint">{detail}</div>}
      </div>
      <div className="shrink-0 whitespace-nowrap text-base font-bold tabular-nums text-accent">{anchor}</div>
    </li>
  );
}

function SectionHeading({ children, caption }: { children: ReactNode; caption?: ReactNode }) {
  return (
    <div className="mb-1">
      <div className="text-xs font-semibold text-muted">{children}</div>
      {caption && <p className="mt-0.5 text-[11px] text-faint">{caption}</p>}
    </div>
  );
}

function MilestonesList({ items }: { items: TeamRecordsMilestone[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <SectionHeading>生涯里程碑</SectionHeading>
      <ul className="divide-y divide-line">
        {items.map((m, i) => (
          <RecordRow
            key={`${m.player_id}-${m.stat}-${i}`}
            headline={<><PlayerLink pid={m.player_id} name={m.name} /><span className="text-muted"> 生涯{m.label}</span></>}
            detail={`目前 ${m.current} → ${m.milestone}`}
            anchor={`還差 ${m.remaining}`}
          />
        ))}
      </ul>
    </div>
  );
}

function StreaksList({ items }: { items: TeamRecordsStreak[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <SectionHeading>進行中連續安打</SectionHeading>
      <ul className="divide-y divide-line">
        {items.map((s) => (
          <RecordRow
            key={s.player_id}
            headline={<><PlayerLink pid={s.player_id} name={s.name} /><span className="text-muted"> 現行連續安打</span></>}
            anchor={`連續 ${s.streak} 場`}
          />
        ))}
      </ul>
    </div>
  );
}

function FranchiseList({ items }: { items: TeamRecordsFranchise[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <SectionHeading caption="僅計數型；資料以年度成績表計，本季貢獻須待球季結束入庫後才會反映，非即時。">
        隊史紀錄逼近
      </SectionHeading>
      <ul className="divide-y divide-line">
        {items.map((r, i) => (
          <RecordRow
            key={`${r.player_id}-${r.stat}-${i}`}
            headline={<><PlayerLink pid={r.player_id} name={r.name} /><span className="text-muted"> {r.label}逼近隊史紀錄</span></>}
            detail={`目前 ${r.current}，隊史紀錄 ${r.record}（${r.holder}）`}
            anchor={`還差 ${r.remaining}`}
          />
        ))}
      </ul>
    </div>
  );
}

export function TeamRecordsSection({ data }: { data: TeamUpcomingRecordsResponse | null }) {
  if (!data) return null;
  const isEmpty = data.milestones.length === 0 && data.streaks.length === 0 && data.franchise_records.length === 0;

  return (
    <Card padding="p-4">
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
        <span className="text-sm font-bold text-ink">即將挑戰的紀錄</span>
      </div>
      {isEmpty ? (
        <EmptyState className="py-3">目前無接近中的紀錄。</EmptyState>
      ) : (
        <div className="space-y-4">
          <MilestonesList items={data.milestones} />
          <StreaksList items={data.streaks} />
          <FranchiseList items={data.franchise_records} />
        </div>
      )}
    </Card>
  );
}
