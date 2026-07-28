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
// 2026-07-28 需求方人工審核第三輪：資料卡讀起來滿意，但要求橫向排列以縮短整頁
// 捲動（原話：「卡片是希望橫向排列 讓這頁資訊能不用卷軸」）。成功條件是量出來的
// 「這頁不用捲軸」，不是「用了 grid」。改成響應式網格，套用本檔案所屬 page.tsx
// 已有的「戰績分項」網格斷點（`grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`，見
// page.tsx `seasonSupporting` 區塊）——同一頁、同樣「把多張小卡片橫向塞進去縮短
// 捲動」的目的，直接沿用同一組斷點而非另訂一套。評估了另外兩個既有積木：
//   - focus-section.tsx 的 `grid-cols-1 md:grid-cols-2` 是固定兩欄（下一場卡＋
//     熱區卡各一），不是「N 筆可變數量」的重複清單網格，形狀不合。
//   - `StatGrid`（ui.tsx）的 `cols` prop 是**無響應式斷點**的固定欄數（cols=3 在
//     375px 也是 3 欄），直接套用會在窄寬度擠爆——違反「375px 無橫向溢出」鐵則，
//     其版面（置中 dl，label 在上 value 在下）也放不下本區塊的四段式內容，故不用。
// 卡片內部版面也一併調整：headline 與 anchor 同列但改頂對齊（`items-start`，
// 因網格變窄後文字更常換行）；headline 移除 `truncate`——需求方明訂「不要
// truncate 掉球員名」，寧可讓描述句換行也不截斷；anchor 仍維持 `shrink-0` 讓它
// 保有固定視覺重量，不被擠壓。

function RecordCard({ headline, detail, anchor }: { headline: ReactNode; detail?: ReactNode; anchor: ReactNode }) {
  return (
    <li className="rounded-lg bg-surface-2 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1 text-sm text-ink">{headline}</div>
        <div className="shrink-0 whitespace-nowrap text-base font-bold tabular-nums text-accent">{anchor}</div>
      </div>
      {detail && <div className="mt-0.5 text-[11px] text-faint">{detail}</div>}
    </li>
  );
}

// 三類共用的網格容器：沿用 page.tsx「戰績分項」的斷點（見上方說明），
// gap-2（非既有的 gap-3）是唯一的刻意偏離——本卡片內距已經比較緊湊
// （px-3 py-2.5，非 Card 的 p-4），沿用 gap-3 視覺上會顯得鬆散不成套。
const RECORD_GRID = "grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3";

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
      <ul className={RECORD_GRID}>
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
      <ul className={RECORD_GRID}>
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
      <ul className={RECORD_GRID}>
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
