import type { ReactNode } from "react";
import { Card, EmptyState, PlayerLink, RECORD_GRID, RecordCard } from "@/components/ui";
import { SubTabs } from "@/components/sub-tabs";
import type {
  TeamRecordsFranchise,
  TeamRecordsFranchiseApproaching,
  TeamRecordsFranchiseRefreshed,
  TeamRecordsMilestone,
  TeamRecordsStreak,
  TeamUpcomingRecordsResponse,
} from "@/lib/api";

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
//
// 2026-07-28 需求方裁定「隊史紀錄的資料延遲與『已刷新』狀態」：後端隊史彙總
// 從「僅 *_seasons、非即時但書」修正為「含本季」，`franchise_records` 從單一
// 形狀改成 `state: "refreshed" | "approaching"` 判別聯集（見 lib/api.ts）。
// 「本季貢獻非即時」但書已隨之移除（修好之後它是假的）。approaching 列若
// `holder_active` 為真，附註「・現役中」——紀錄保持人還在打球時這個數字本身
// 會隨賽季推進而動，不是靜止的碑（台鋼雄鷹是典型案例）。

// `RecordCard`/`SectionHeading`/`RECORD_GRID` 的設計理由（bg-surface-2 無 border
// 避免卡中卡、橫向網格斷點沿用 page.tsx「戰績分項」）已隨 UX-TEAM-HOTZONE1
// 一併抽到 `@/components/ui`（該卡新增的「近期球員熱區」也要用同一套語彙，
// 抽成單一事實來源避免兩檔各自維護一份視覺 token）；本檔案只留呼叫端。
//
// 2026-07-28 需求方追加：三分類（生涯里程碑／進行中連續安打／隊史紀錄）改小
// 頁籤切換（`SubTabs`，見該元件 docstring），一次只顯示一個分類——內容多的
// 球隊（如台鋼同週 6+ 筆隊史新高）原本三段疊加會撐爆 1440×1080 版面。
// 「空分類不出現頁籤」延續 RECORDS1 原定案的「空分類整段隱藏」，只是從
// 「整段不渲染」變成「不出現在頁籤列」，讀者仍能從頁籤列看到有哪幾類、
// 自己切換，不是靜默省略（與紅線「不得為了塞進畫面刪減資訊」不衝突）。
//
// 每個分類清單不再各自帶 `SectionHeading`——分類名稱已經是頁籤文字，清單內
// 再標一次是重複資訊（同一種理由已用於熱區卡：headline 不重複區段標題）。
//
// 2026-07-28 需求方追加：改用 `RecordCard` 的 `layout="stack"` 版型＋
// `RECORD_GRID`（3 欄，取代先前的 `RECORD_GRID_2COL` 過渡版本）——原因與寬度
// 實證見 `ui.tsx` `RecordCard` docstring（全聯盟最壞字寬組合在 2 欄/row 版下
// 仍會斷字，3 欄/stack 版才安全）。`ApproachingCard` 的 label 從「{項目}逼近
// 隊史紀錄」簡化為單純「{項目}」（與 RefreshedCard 一致）——「逼近」與「已
// 刷新」兩種狀態已經由 anchor（「還差 N」vs.「隊史新高」）唯一區分，label 重複
// 講一次是冗字，stack 版每字都在跟 165px 欄寬搶空間，能省則省。

function MilestonesList({ items }: { items: TeamRecordsMilestone[] }) {
  return (
    <ul className={RECORD_GRID}>
      {items.map((m, i) => (
        <RecordCard
          layout="stack"
          key={`${m.player_id}-${m.stat}-${i}`}
          label={`生涯${m.label}`}
          name={<PlayerLink pid={m.player_id} name={m.name} />}
          detail={`目前 ${m.current} → ${m.milestone}`}
          anchor={`還差 ${m.remaining}`}
        />
      ))}
    </ul>
  );
}

function StreaksList({ items }: { items: TeamRecordsStreak[] }) {
  return (
    <ul className={RECORD_GRID}>
      {items.map((s) => (
        <RecordCard
          layout="stack"
          key={s.player_id}
          label="現行連續安打"
          name={<PlayerLink pid={s.player_id} name={s.name} />}
          anchor={`連續 ${s.streak} 場`}
        />
      ))}
    </ul>
  );
}

function RefreshedCard({ r }: { r: TeamRecordsFranchiseRefreshed }) {
  return (
    <RecordCard
      layout="stack"
      label={r.label}
      name={<PlayerLink pid={r.player_id} name={r.name} />}
      detail={`目前 ${r.current}，原紀錄 ${r.prior_record}（${r.prior_holder}）`}
      anchor="隊史新高"
    />
  );
}

function ApproachingCard({ r }: { r: TeamRecordsFranchiseApproaching }) {
  const holder = r.holder_active ? `${r.holder}・現役中` : r.holder;
  return (
    <RecordCard
      layout="stack"
      label={r.label}
      name={<PlayerLink pid={r.player_id} name={r.name} />}
      detail={`目前 ${r.current}，隊史紀錄 ${r.record}（${holder}）`}
      anchor={`還差 ${r.remaining}`}
    />
  );
}

function FranchiseList({ items }: { items: TeamRecordsFranchise[] }) {
  return (
    <ul className={RECORD_GRID}>
      {items.map((r, i) => (
        r.state === "refreshed"
          ? <RefreshedCard key={`${r.player_id}-${r.stat}-${i}`} r={r} />
          : <ApproachingCard key={`${r.player_id}-${r.stat}-${i}`} r={r} />
      ))}
    </ul>
  );
}

type RecordsCategory = "milestones" | "streaks" | "franchise";

export function TeamRecordsSection({ data }: { data: TeamUpcomingRecordsResponse | null }) {
  if (!data) return null;
  const isEmpty = data.milestones.length === 0 && data.streaks.length === 0 && data.franchise_records.length === 0;

  // 固定順序（生涯里程碑→進行中連續安打→隊史紀錄）、只收非空分類；預設分類＝
  // 固定順序第一個非空——不是「筆數最多」，切換球隊時頁籤預設落點才不會跳
  // （需求方明訂，見卡面 UX-TEAM-HOTZONE1）。
  const categories: { value: RecordsCategory; label: string; content: ReactNode }[] = [];
  if (data.milestones.length > 0) {
    categories.push({ value: "milestones", label: "生涯里程碑", content: <MilestonesList items={data.milestones} /> });
  }
  if (data.streaks.length > 0) {
    categories.push({ value: "streaks", label: "進行中連續安打", content: <StreaksList items={data.streaks} /> });
  }
  if (data.franchise_records.length > 0) {
    categories.push({ value: "franchise", label: "隊史紀錄", content: <FranchiseList items={data.franchise_records} /> });
  }

  return (
    <Card padding="p-4">
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
        <span className="text-sm font-bold text-ink">即將挑戰的紀錄</span>
      </div>
      {isEmpty ? (
        <EmptyState className="py-3">目前無接近中的紀錄。</EmptyState>
      ) : (
        <SubTabs label="即將挑戰的紀錄分類" items={categories} defaultValue={categories[0].value} />
      )}
    </Card>
  );
}
