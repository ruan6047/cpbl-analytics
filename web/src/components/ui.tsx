import Link from "next/link";
import type { ReactNode } from "react";
import { codeFromName, eraBadge, isCurrentTeam, teamPageCode } from "@/lib/teams";
import { LetterMark, TeamIcon } from "./postmark";
import { Tooltip } from "./tooltip";

// 實體連結 pattern（UI_UX_SYSTEM §3；UX-ENTITY-LINKS1）：球員/球隊等「實體名」連結
// 走沉穩色 text-ink ＋ 常駐細底線（非色彩單獨可辨識，a11y），hover 才轉 accent。
// 刻意不用 accent 紅——accent 同時是行動色＋數據差(down)色，紅字實體名觀感突兀。
// 「行動連結」（看單場→／導覽／CTA）另保留 accent 紅，不套此 pattern。
export const ENTITY_LINK =
  "text-ink underline decoration-line decoration-1 underline-offset-2 transition-colors hover:text-accent hover:decoration-accent";

// 給「外層已經有 <Link> 包住整塊（logo＋名稱／整張卡／整顆 chip）」的呼叫點：
// 只把 ENTITY_LINK 的**視覺**套在名稱文字上，本身不自建 <a>——可點範圍維持原樣
// （卡面 UX-ENTITY-LINKS2「不改可點範圍語意」；§3.5 要的是「只有文字帶底線」，
// 不是「只有文字可點」），也不會產生 nested <a>。
// 外層 <Link> 需帶 `group`，hover 才會從整塊觸發而非只在文字上。
export const ENTITY_LINK_TEXT =
  `${ENTITY_LINK} group-hover:text-accent group-hover:decoration-accent`;

// 字母方塊徽章（單一事實來源）：給定 {color, letter} 渲染隊色底＋對比字。
// #220 起只承載「沒有核可印記」的隊（歷史／已解散隊、沿革各時期），樣式＝postmark.tsx 的
// LetterMark（紙面 3px 圓角）；現役六隊一律走 TeamLogo → 核可印記。
export function LetterBadge({ meta, size = 16 }: { meta: { color: string; letter: string }; size?: number; round?: boolean }) {
  return <LetterMark color={meta.color} letter={meta.letter} size={size} />;
}

// 沿革／歷史隊徽章：隊名 + 代碼 → eraBadge（歷史隊 iconic 色），渲染字母方塊。
export function EraBadge({ name, code, size = 16 }: { name: string; code: string; size?: number }) {
  return <LetterBadge meta={eraBadge(name, code)} size={size} />;
}

// 依隊名渲染徽章 + 名稱（走 nameMeta 統一解析，含歷史/二軍隊）。
// 隊名徽章＋名稱。link=true 時隊名文字連 /teams（§9.3；opt-in，避免既有呼叫點
// 若已在 <Link> 內產生 nested <a>）。歷史/已解散隊（無現役 franchise）自動不連。
// 只有名稱文字帶連結＋底線，logo 不套（底線橫跨徽章觀感差）。
export function NameTag({ name, size = 16, link = false }: { name?: string | null; size?: number; link?: boolean }) {
  const code = link ? codeFromName(name) : null;
  const href = code && isCurrentTeam(code) ? `/teams/${teamPageCode(code)}` : null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <TeamLogo name={name} size={size} decorative />
      {href ? <Link href={href} className={ENTITY_LINK}>{name}</Link> : <span>{name || "—"}</span>}
    </span>
  );
}

// 球員連結（無 player_id 時退化為純文字）。預設走實體連結 pattern（§3；不再紅字）。
export function PlayerLink({ pid, name, className = ENTITY_LINK }: { pid?: string | null; name: string; className?: string }) {
  return pid ? <Link href={`/players/${pid}`} className={className}>{name}</Link> : <>{name}</>;
}

// 身分標籤（#218 `.tag`）：現役／已解散、教練、連霸等分類。細字淡底，不與狀態章混用；
// tone="up"（現役）只加深字色，不另起一個語意色。
export function Pill({ children, tone = "muted", className = "" }: { children: React.ReactNode; tone?: "up" | "muted"; className?: string }) {
  return <span className={`pm-tag ${tone === "up" ? "!text-ink" : ""} ${className}`}>{children}</span>;
}
export const ActivePill = ({ className = "" }: { className?: string }) => <Pill tone="up" className={className}>現役</Pill>;
export const GonePill = ({ className = "" }: { className?: string }) => <Pill tone="muted" className={className}>已解散</Pill>;

// 隊伍圖示：現役六隊＝#218 核可的紙面單色印記（非官方隊徽）；歷史／已解散隊沒有核可印記，
// 沿用字母章（隊名優先解析，含 era 色）。實作在 postmark.tsx 的 TeamIcon（單一入口）。
// decorative：圖示旁已顯示隊名時（NameTag/TeamBadge）設 true → aria-hidden，避免
// 螢幕閱讀器重複念隊名。獨立使用（如對戰矩陣表頭僅圖示）則保留 aria-label。
export function TeamLogo({ code, name, size = 24, decorative = false }: { code?: string | null; name?: string | null; size?: number; decorative?: boolean }) {
  return <TeamIcon code={code} name={name} size={size} label={decorative ? undefined : `${name ?? code ?? ""}隊徽`} />;
}

// 卡殼單一事實來源（.card＝surface 卡面色塊＋4px 圓角；#218 起不畫框、不加陰影）。
// padding 預設 p-4，可覆寫（p-3 / "px-4 py-3" / "" 無內距如包表格）。全站禁再手寫
// `rounded-xl border border-line`，一律走此元件（特例：DataTable/leaderboard 內建表殼、
// <details> 折疊、game-board ESPN 內部面板）。
export function Card({ className = "", padding = "p-4", teamColor, hoverable = false, children }: { className?: string; padding?: string; teamColor?: string; hoverable?: boolean; children: React.ReactNode }) {
  const style = teamColor ? { "--hover-color": teamColor } as React.CSSProperties : undefined;
  const shouldHover = hoverable || !!teamColor;
  return (
    <div style={style} className={`card ${padding} ${shouldHover ? "card-hover-team" : ""} ${className}`}>
      {children}
    </div>
  );
}

// 橫向排版：標籤在左、數值＋名次在右，一磚一列以節省縱向空間。
export function StatTile({ label, value, accent, rank, rankTotal }: {
  label: string; value: string; accent?: boolean;
  /** 聯盟名次（有值才顯示）。前段班綠、後段班紅、其餘淡色。 */
  rank?: number | null;
  /** 隊伍總數，用於判定「後段班」。 */
  rankTotal?: number;
}) {
  const tone = rank == null ? "" : rank <= 2 ? "text-up"
    : rankTotal && rank >= rankTotal - 1 ? "text-down" : "text-faint";
  return (
    <div className="card flex items-baseline justify-between gap-1.5 overflow-hidden px-3 py-2">
      <span className="min-w-0 truncate text-[11px] text-muted">{label}</span>
      <span className="flex shrink-0 items-baseline gap-1 whitespace-nowrap">
        <span className={`font-mono text-base tabular-nums ${accent ? "text-accent" : "text-ink"}`}>{value}</span>
        {rank != null && <span className={`text-[10px] font-medium tabular-nums ${tone}`}>第{rank}</span>}
      </span>
    </div>
  );
}

// link=true 時隊名文字連 /teams（§9.3；歷史/已解散隊自動不連）。
// linkStyle=true：外層呼叫點已自備 <Link> 包住整塊，此處只給名稱文字 ENTITY_LINK 的
// 視覺、不自建 <a>（見 ENTITY_LINK_TEXT）。與 link 互斥——link 自建錨點、linkStyle 不。
export function TeamBadge({ code, name, size = 20, link = false, linkStyle = false }: { code?: string | null; name?: string | null; size?: number; link?: boolean; linkStyle?: boolean }) {
  const href = link && isCurrentTeam(code) ? `/teams/${teamPageCode(code)}` : null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <TeamLogo code={code} name={name} size={size} decorative={!!name} />
      {name && (href
        ? <Link href={href} className={ENTITY_LINK}>{name}</Link>
        : <span className={linkStyle ? ENTITY_LINK_TEXT : undefined}>{name}</span>)}
    </span>
  );
}

// 區塊標題（#218：全站一套、不加眉標）。歷史名稱保留為 Eyebrow 以免全站改名，視覺已改為
// 次標（16px 粗體墨色、無大寫字距）；新程式請用 postmark.tsx 的 SectionTitle（含 h2/h3 語意）。
export function Eyebrow({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`text-base font-bold leading-snug tracking-[0.04em] text-ink ${className}`}>{children}</div>;
}

// dl 堆疊網格（決勝資訊式）：label 上、value 下，等寬數字。取代散寫的 label/value 對。
export function StatGrid({ items, cols = 2, className = "" }: {
  items: { label: React.ReactNode; value: React.ReactNode; tone?: "accent" | "muted" }[];
  cols?: 2 | 3 | 4 | 5;
  className?: string;
}) {
  const colCls = { 2: "grid-cols-2", 3: "grid-cols-3", 4: "grid-cols-4", 5: "grid-cols-5" }[cols];
  return (
    <dl className={`grid ${colCls} gap-2 ${className}`}>
      {items.map((it, i) => (
        <div key={i} className="rounded-md bg-surface-2 px-3 py-2 text-center">
          <dt className="text-[11px] text-muted">{it.label}</dt>
          <dd className={`mt-0.5 font-mono text-lg tabular-nums ${it.tone === "accent" ? "text-accent" : it.tone === "muted" ? "text-muted" : "text-ink"}`}>{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

// 「近日焦點」頁籤資料卡語彙（UX-TEAM-RECORDS1 定案，UX-TEAM-HOTZONE1 沿用）：
// 每筆一張次級卡。兩種版型共用同一個元件（`layout` 判別聯集 prop，而非複製一份
// 新元件——2026-07-28 需求方明訂「不要用 copy-paste 分岔」）：
//
// - `layout="row"`（預設，近期球員熱區沿用）：headline 描述句＋右側單一數值錨點
//   同一行。熱區的文字短（球員名 2-4 字＋「km/h」「%」），3 欄綽綽有餘，換版型
//   對它只有壞處沒有好處，故不動。
// - `layout="stack"`（即將挑戰的紀錄專用）：**三行**——第一行項目名（靠左）
//   ＋錨點（靠右，同行）、第二行球員名、第三行（選填）明細。改版型不是為了
//   省空間（stack 版每卡仍比熱區的 row 版高，見下方 grep 得到的卡面 log）——
//   是因為 row 版在窄欄位下即使兩行也裝不下全聯盟最壞字寬組合（見下）。
//
// 2026-07-28 需求方原本要求四行（項目名／球員名／錨點／明細各自一行，原話
// 見下方 canvas 實測），人工審看過後追加一輪要求「錨點移到項目名右側同一
// 行」（省一行高度、視覺更緊湊），**但字級不縮到 12px**——錨點維持
// `text-sm font-bold text-accent`：粗體＋accent 色是唯一的重量來源，不靠
// 字級（若跟球員名同為 14px 且都不加粗，兩者會打架；加粗＋變色讓錨點讀起來
// 像狀態徽章，不是第二個標題）。仍只用 `text-xs`/`text-sm` 兩級，零新增
// arbitrary 字級。
//
// **為什麼要垂直堆疊、不是靠加寬欄位或縮字**：需求方 2026-07-28 用 canvas 實測
// 全聯盟最壞值——最長球員名 112px（`伊斯坦大．比力安`／`田中怜利ハモンド`）、
// 精簡後最長項目名 60px（`救援／中繼`，text-xs/12px）、最長錨點在
// text-sm/14px 粗體下約 58px（`連續 5 場`）。項目名的最壞值**取決於 label
// 是否還帶著跟 SubTabs 頁籤重複的前綴**（見 records-section.tsx 的三處
// label 簡化）：
//
// | 版型 | 現況標籤（帶前綴，已淘汰） | 精簡標籤後（已淘汰的四行 stack） | 精簡標籤＋錨點同行（現況三行 stack） |
// |---|---|---|---|
// | row 單行 | 369px | 285px | — |
// | row 兩行 | 252px | 168px | — |
// | stack 第一行（項目+錨點同行）／整卡 | 178px（四行版） | 136px（四行版） | 60+8+58=126px |
// | stack 第二行（球員名） | — | — | 112px |
//
// 半寬左欄 3 欄實得寬度僅 ~165px（含內距）。**帶前綴時連四行 stack 版都裝
// 不下（178 > 165）**——第一輪算寬度時漏算了 franchise 的 approaching 變體
// （`{項目}逼近隊史紀錄`，最長組合「救援／中繼逼近隊史紀錄」154px）。**拿掉
// 前綴（label 精簡）因此不是可有可無的美觀調整，是 3 欄／stack 版能成立的
// 前提**。現況三行版單卡需求寬＝max(126, 112)+24（內距）＝150px，165px 尚
// 有 15px 餘裕——比四行版的 29px 餘裕更緊，故本輪務必用最壞組合（`伊斯坦大．
// 比力安`＋`救援／中繼`＋`連續 5 場`）實測，不能只看今天在榜的名字。
//
// 為什麼是 bg-surface-2 + rounded-lg（無 border）而不是再套一層 <Card>：這組卡片
// 永遠巢狀在頁籤的外層 <Card> 裡，若每筆也用 Card 會變成卡中卡（.card 的
// border-line + shadow 疊兩層）。設計系統只對 DataTable 定義了等價的 `bare`
// （同問題的既有解法：已在 Card 內免雙層邊框），Card 本身沒有等價 prop——
// 評估過幫 Card 加 `bare`/`nested` prop，但這個場景的呼叫點不夠多，屬過度設計。
// 改沿用 `StatGrid` 已驗證過的「bg-surface-2 + rounded-lg」次級 surface token
// （同一份視覺語彙，但 StatGrid 本身版面置中 dl 放不下這裡需要的四段式內容，
// 故不直接套用元件，只借它驗證過的容器語彙）。
type RecordCardRowProps = { layout?: "row"; headline: ReactNode; detail?: ReactNode; anchor: ReactNode };
type RecordCardStackProps = { layout: "stack"; label: ReactNode; name: ReactNode; detail?: ReactNode; anchor: ReactNode };

export function RecordCard(props: RecordCardRowProps | RecordCardStackProps) {
  if (props.layout === "stack") {
    return (
      <li className="rounded-lg bg-surface-2 px-3 py-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <div className="min-w-0 truncate text-xs text-muted">{props.label}</div>
          <div className="shrink-0 whitespace-nowrap text-sm font-bold tabular-nums text-accent">{props.anchor}</div>
        </div>
        <div className="mt-0.5 text-sm text-ink">{props.name}</div>
        {props.detail && <div className="mt-0.5 text-xs text-faint">{props.detail}</div>}
      </li>
    );
  }
  const { headline, detail, anchor } = props;
  return (
    <li className="rounded-lg bg-surface-2 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1 text-sm text-ink">{headline}</div>
        <div className="shrink-0 whitespace-nowrap text-base font-bold tabular-nums text-accent">{anchor}</div>
      </div>
      {detail && <div className="mt-0.5 text-xs text-faint">{detail}</div>}
    </li>
  );
}

// 密排行內用的資訊小圓點觸發鈕（"i"）：包一層 `Tooltip`，用於卡片明細行內聯
// 「還有更多但不想佔常駐版位」的場景（原始案例：focus-section.tsx 熱區卡的
// 次要數據；UX-TEAM-HOTZONE1 追加案例：records-section.tsx 隊史刷新卡的原
// 紀錄段落）。第二個呼叫點出現後從各自檔案內的區域函式抽成這裡的共用元件，
// 避免同一段「觸控熱區補到 24px 但不放大視覺圖示」的 CSS 手法各自維護一份、
// 日後不同步走鐘。
//
// 視覺 14px 圖示（`h-3.5 w-3.5`）、字級 `text-[10px]`（UI_UX_SYSTEM §2.3：
// sub-9px 低於可讀下限，10px 對應既有 `micro` 角色）；`relative`＋`::before`
// 負 inset（-5px，14+5+5=24）撐出 WCAG 2.5.8 的 24×24 熱區——**不用**
// `ContextSwitcher` 的 `min-h-11` 真實撐大（那招適合獨立工具列，這裡是密排
// 行內元素，真的撐到 44px 會把整條明細行/標題列一起拉高）。`aria-label`
// 必須由呼叫端帶對象具體敘述（如「三振 原紀錄保持人」），不得省略——省略會
// 退回 `Tooltip` 對「非空文字內容」的預設判定，把字面「i」讀成可及名稱
// （UX-TEAM-HOTZONE1 修過的真實 bug，見 `tooltip.tsx` cloneElement 註解）。
export function InfoDot({ label, content, hiddenBelowMd }: {
  label: string; content: ReactNode;
  /** 熱區卡的原始用法：<768px 次要數據常駐顯示（單欄有空間），≥768px 才換成
   * 這顆觸發鈕，兩者互斥（見 focus-section.tsx CardDetail）。預設一律顯示。 */
  hiddenBelowMd?: boolean;
}) {
  const display = hiddenBelowMd ? "hidden md:grid" : "inline-grid";
  return (
    <Tooltip content={content} suppressUnderline interactive>
      <button type="button" aria-label={label}
        className={`relative ${display} h-3.5 w-3.5 shrink-0 touch-manipulation place-items-center rounded-full border border-line text-[10px] font-semibold leading-none text-muted before:absolute before:-inset-[5px] before:content-[''] hover:text-ink`}>
        i
      </button>
    </Tooltip>
  );
}

// RecordCard 清單的共用網格斷點：橫向排列縮短整頁捲動（需求方 2026-07-28 明訂
// 「卡片是希望橫向排列 讓這頁資訊能不用卷軸」）。與 page.tsx「戰績分項」網格
// 同一組斷點，同一頁同樣「把多張小卡片橫向塞進去縮短捲動」的目的不另訂一套。
// gap-2（非其他網格常用的 gap-3）是唯一刻意偏離：RecordCard 內距已較緊湊
// （px-3 py-2.5，非 Card 的 p-4），沿用 gap-3 視覺上會顯得鬆散不成套。
//
// `lg:grid-cols-3` 是**viewport 斷點，不是容器斷點**——只在「這份清單佔滿頁面
// 全寬」的前提下 3 欄才有實得寬度。半寬欄位（如「即將挑戰的紀錄」現在永遠
// 位於 focus-section.tsx 的半寬左欄）viewport lg 仍會觸發、每卡實得寬度只剩
// 一半（1440 實測 546px 卡寬 ÷3≈165px）——這曾是三輪真實 bug 的成因：
//   1. 第一輪退回：row 版錨點 shrink-0 nowrap 擠壓 headline，逐字斷行。
//   2. 第二輪一度改用 2 欄暫時避開，但那只是「降欄數換寬度」的權宜——本質
//      問題（欄寬 vs. 文字最壞寬度）沒解。
//   3. 第三輪重算最壞字寬時發現第二輪的估計本身也低估了（漏算 franchise
//      approaching 變體的 label 後綴），帶前綴的標籤下即使 stack 版也要
//      178px，仍超過 165px——真正解法不是欄數/版型，是先把跟頁籤名重複的
//      label 前綴拿掉（見 records-section.tsx），把 stack 版壓到 136px
//      才低於 165px 的真實欄寬（見上方 RecordCard docstring 的完整實測表）。
// 現在 `layout="stack"` + 精簡後的 label 把單卡最壞需求壓到 136px（< 165px），
// 3 欄本身重新安全，故「即將挑戰的紀錄」與「近期球員熱區」統一用回這一個
// `RECORD_GRID`（不再需要曾經存在的 `RECORD_GRID_2COL` 過渡版本，已移除）。
export const RECORD_GRID = "grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3";

export function SectionHeading({ children, caption }: { children: ReactNode; caption?: ReactNode }) {
  return (
    <div className="mb-1">
      <div className="text-sm font-bold tracking-[0.04em] text-ink">{children}</div>
      {caption && <p className="mt-0.5 text-xs text-faint">{caption}</p>}
    </div>
  );
}

// —— 感知效能三態（skeleton / empty / error）：全站統一，取代各檔散寫的
//    「載入中…」「無資料」與 ad-hoc 佔位（原則 8）。皆 server-safe。
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-2 ${className}`} aria-hidden />;
}
// 表格骨架：rows×cols 個灰塊，切換資料時不佈局塌陷（CLS）。
export function TableSkeleton({ rows = 5, cols = 4, className = "" }: { rows?: number; cols?: number; className?: string }) {
  return (
    <div className={`overflow-hidden rounded-md bg-surface ${className}`} aria-hidden>
      <div className="flex gap-3 bg-band px-3 py-2.5">
        {Array.from({ length: cols }).map((_, i) => <Skeleton key={i} className="h-4 flex-1" />)}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3 px-3 py-2.5">
          {Array.from({ length: cols }).map((_, i) => <Skeleton key={i} className="h-4 flex-1" />)}
        </div>
      ))}
    </div>
  );
}
export function EmptyState({ children = "無資料", className = "" }: { children?: React.ReactNode; className?: string }) {
  return <p className={`py-8 text-center text-sm text-faint ${className}`}>{children}</p>;
}
export function ErrorState({ children = "載入失敗", className = "" }: { children?: React.ReactNode; className?: string }) {
  return <p className={`py-8 text-center text-sm text-down ${className}`} role="alert">{children}</p>;
}

// 場次狀態章（#218 `.st`）：全站唯一狀態語彙，必含文字。done＝終場、scheduled＝賽前（中性章）；
// live＝進行中（石油藍實底＋脈動點）；warn＝延賽・保留・中斷（紅字章，down 色）。
export type StatusTone = "done" | "warn" | "live" | "scheduled";
const STATUS_TONE_CLS: Record<StatusTone, { solid: string; bare: string }> = {
  done: { solid: "pm-st", bare: "text-muted" },
  warn: { solid: "pm-st pm-st--hold", bare: "text-down" },
  live: { solid: "pm-st pm-st--live pm-updating", bare: "text-accent" },
  scheduled: { solid: "pm-st", bare: "text-muted" },
};
// variant solid＝狀態章（列表）；bare＝純色文字（月曆格等窄空間）。兩型共用 tone→色。
export function StatusBadge({ children, tone, variant = "solid", className = "" }: {
  children: React.ReactNode; tone: StatusTone; variant?: "solid" | "bare"; className?: string;
}) {
  const t = STATUS_TONE_CLS[tone];
  return variant === "bare"
    ? <span className={`font-bold leading-none ${t.bare} ${className}`}>{children}</span>
    : <span className={`${t.solid} ${className}`}>{children}</span>;
}

// 提示附註（#218「限制」附註：淡色塊＋粗體標籤＋說明）。警示不用 emoji：label 是一個文字章
// （延賽／保留用紅字章，其餘中性），內文維持原句。
export function Notice({ tone = "warn", label, children, className = "" }: {
  tone?: "warn" | "hold"; label?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-md bg-surface-2 px-4 py-2.5 text-sm text-ink ${className}`}>
      {label != null && <span className={`pm-st ${tone === "hold" ? "pm-st--hold" : ""}`}>{label}</span>}
      <span>{children}</span>
    </div>
  );
}

// 百分位發散色階：0=藍 50=灰 100=紅（Baseball Savant 式）
export function prColor(pr: number): string {
  const lerp = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);
  const hex = (r: number, g: number, b: number) => `rgb(${r},${g},${b})`;
  if (pr <= 50) {
    const t = pr / 50; // #1E5BB8 → #E8E8E8
    return hex(lerp(30, 232, t), lerp(91, 232, t), lerp(184, 232, t));
  }
  const t = (pr - 50) / 50; // #E8E8E8 → #C4122F
  return hex(lerp(232, 196, t), lerp(232, 18, t), lerp(232, 47, t));
}

// prColor 發散色階的 CSS gradient（圖例用；端點對齊 prColor 0/50/100）。固定 data-viz 色階，深淺共用。
export const PR_GRADIENT = "linear-gradient(90deg, rgb(30,91,184), rgb(232,232,232), rgb(196,18,47))";

// prColor 色格上的文字色：格底恆為淺色（藍↔白↔紅），故文字固定深墨+白 halo，不隨主題翻轉
// （用 ct.ink 會在深色模式變成淺字疊在淺格上）。
export const PR_CELL_TEXT = { ink: "#0a2540", halo: "#ffffff" };

/** 選手頁官方 PR 條（#218 核可：單色）。條長＝聯盟百分位，石油藍只標 PR 90 以上，其餘墨灰；
 *  方向沿用官方 PR（高＝有利）。排行／戰績／熱度圖的發散色另由 prColor 承載，語意不同不合併。 */
export function PercentileBar({ name, value, pr, def }: { name: string; value: string; pr: number; def?: string }) {
  // 定義提示走共用 Tooltip（原生 title 有延遲且觸控無效）
  const label = <span className="w-[6.5em] shrink-0 truncate">{name}</span>;
  return (
    <div className="flex items-center gap-2.5 text-[13px]">
      {def ? <Tooltip content={def}>{label}</Tooltip> : label}
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-band">
        <div className={`h-full rounded-full ${pr >= 90 ? "bg-accent" : "bg-muted"}`} style={{ width: `${Math.max(0, Math.min(pr, 100))}%` }} />
      </div>
      <span className="w-[4em] shrink-0 text-right font-mono tabular-nums text-ink">{value}</span>
      <span className="w-[2.4em] shrink-0 text-right font-mono font-bold tabular-nums text-ink">{pr}</span>
    </div>
  );
}

// 發散上色（Savant 式淡底）：值在 vals 值域內線性 0-100 → prColor；lowerBetter 反向。
// 值缺、樣本 <2 或值域為零時不上色。回傳可直接掛在 <td style> 的物件。
export function divBg(v: number | null | undefined, vals: (number | null | undefined)[],
                      lowerBetter = false): React.CSSProperties | undefined {
  if (v == null) return undefined;
  const nums = vals.filter((x): x is number => x != null && Number.isFinite(x));
  if (nums.length < 2) return undefined;
  const min = Math.min(...nums), max = Math.max(...nums);
  if (max <= min) return undefined;
  let p = (v - min) / (max - min);
  if (lowerBetter) p = 1 - p;
  return { background: prColor(p * 100).replace("rgb", "rgba").replace(")", ",0.28)") };
}

// 進階數據名詞解釋對照表 (Common Baseball Advanced Metrics dictionary)
export const METRIC_DESCRIPTIONS: Record<string, string> = {
  OPS: "整體攻擊指數 (On-base Plus Slugging) = 上壘率 + 長打率，用以衡量打者的綜合進攻生產力能力。",
  ERA: "防禦率 (Earned Run Average) = 自責分 × 9 ÷ 投球局數，代表投手每九局自責分。",
  WHIP: "每局被上壘率 (Walks plus Hits per Inning Pitcher) = (安打 + 四壞) ÷ 投球局數，衡量投手控制被上壘的能力。",
  "wRC+": "加權得分創造值 (Weighted Runs Created Plus) = 經球場與聯盟環境調整後的得分創造指數，100 為聯盟平均，越高越強。",
  FIP: "獨立防禦率 (Fielding Independent Pitching) = 衡量投手自身純粹三振、保送、被全壘打的防禦率，排除守備與運氣因素。",
  xwOBA: "預期加權上壘率 (Expected Weighted On-Base Average) = 依擊球初速與仰角計算的預期上壘價值，代表打者真實擊球品質。",
  WAR: "替代值勝場數 (Wins Above Replacement) = 相比替補球員，該球員能為球隊多帶來幾場勝利的綜合貢獻值。",
  BABIP: "場內安打率 (Batting Average on Balls In Play) = 球打進場內形成安打的機率，可用來觀察運氣或守備影響度。",
  IsoP: "純長打率 (Isolated Power) = 長打率 - 打擊率，純粹衡量打者擊出長打的威力。",
  BB: "四壞球保送次數 (Base on Balls)。",
  SO: "三振次數 (Strikeout)。",
  AVG: "打擊率 (Batting Average) = 安打 ÷ 打數。",
  OBP: "上壘率 (On-base Percentage) = (安打 + 四壞 + 觸身) ÷ (打數 + 四壞 + 觸身 + 犧牲飛球)。",
  SLG: "長打率 (Slugging Percentage) = 意指二壘安打/三壘安打/全壘打折合之壘打數 ÷ 打數。",
  "OPS+": "調整攻擊指數 (OPS Plus) = OPS 經聯盟環境調整後的指數，100 為聯盟平均，120 代表優於平均 20%。",
  "ERA+": "調整防禦率 (ERA Plus) = 聯盟平均 ERA 相對本人 ERA 的指數，100 為聯盟平均，越高越好。",
  K9: "每九局三振數 (Strikeouts per 9 Innings) = 三振 × 9 ÷ 投球局數。",
};

export function StatAbbr({
  abbr,
  customDesc,
  className = "",
  suppressUnderline = false,
}: {
  abbr: string;
  customDesc?: string;
  className?: string;
  suppressUnderline?: boolean;
}) {
  const desc = customDesc || METRIC_DESCRIPTIONS[abbr];
  if (!desc) return <span className={className}>{abbr}</span>;
  return (
    <Tooltip content={desc} suppressUnderline={suppressUnderline}>
      <span className={className}>{abbr}</span>
    </Tooltip>
  );
}
