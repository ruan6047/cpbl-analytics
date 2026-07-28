import type { ReactNode } from "react";
import { Card, EmptyState, PlayerLink } from "@/components/ui";
import type { TeamRecordsFranchise, TeamRecordsMilestone, TeamRecordsStreak, TeamUpcomingRecordsResponse } from "@/lib/api";

// 近日焦點・即將挑戰的紀錄（UX-TEAM-RECORDS1）。
//
// 2026-07-28 需求方人工審核第二輪：句式列版本讀者反應正面，但要求改成「資料卡」
// 容器（原話：「想改成資料卡的形式呈現」）。句式列本身（每筆一句話、「還差 N」
// 唯一錨點、目前/目標退次級、空分類整段隱藏）全部保留，只換每筆的容器外觀。
//
// 雙層邊框處理：整個區塊本身已是最外層的 <Card>（見本檔案最下方），若每筆改用
// `Card` 元件會變成卡中卡（.card 的 border-line + shadow 疊兩層）。設計系統
// §「共通」只對 DataTable 定義了 `bare`（同問題的既有解法：已在 Card 內免雙層
// 邊框），Card 本身沒有等價 prop。評估了三個方向：
//   (a) 外層改用非 Card 容器、讓每筆用真正的 <Card>——會讓這個區塊在「近日焦點」
//       頁籤裡失去跟「下一場」「近期球員熱區」兩張手足 Card 一致的外框，犧牲頁面
//       層級的視覺一致性換取單筆卡片內部一致性，不划算。
//   (b) 幫 Card 加一個等價 `bare`/`nested` prop——這個場景只有本檔案用得到，
//       為單一呼叫點擴充全站唯一事實來源的公開 API 有過度設計之嫌。
//   (c) 每筆用**既有的次級 surface token**（`bg-surface-2` + `rounded-lg`，
//       無 border）——`StatGrid`（ui.tsx）已用同一組 token 處理「Card 內要再分出
//       一格一格」的場景（如球員頁「決勝資訊」），是本專案既有慣例，不是新發明。
// 採用 (c)：`StatGrid`/`StatTile` 本身的版面（label 在上、置中的 value，或
// label 左 value 右單行）放不下本區塊需要的「球員連結＋描述句＋次級明細行＋
// 右側大字錨點」四段式內容，所以不直接套用元件本身，但沿用它驗證過的
// 「bg-surface-2 + rounded-lg（無 border）」視覺語彙組出符合本區塊內容形狀的卡片。
//
// 其餘不變：三類共用同一個 <RecordCard>（同一套排版節奏，不做成三種元件）；
// 「還差 N」／「連續 N 場」是唯一視覺錨點；沒有內容的子分類整段不渲染；三類
// 全空時顯示整區塊統一退化文案；隊史「本季貢獻非即時」的但書跟著該分類走；
// 生涯口徑／里程碑門檻／隊史逼近門檻與判準全部不變（後端一行未改動）。

function RecordCard({ headline, detail, anchor }: { headline: ReactNode; detail?: ReactNode; anchor: ReactNode }) {
  return (
    <li className="flex items-center gap-3 rounded-lg bg-surface-2 px-3 py-2.5">
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
      <ul className="space-y-1.5">
        {items.map((m, i) => (
          <RecordCard
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
      <ul className="space-y-1.5">
        {items.map((s) => (
          <RecordCard
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
      <ul className="space-y-1.5">
        {items.map((r, i) => (
          <RecordCard
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
