import Link from "next/link";
import type { ReactNode } from "react";
import { codeFromName, contrastText, eraBadge, isCurrentTeam, nameMeta, teamColor, teamLetter, teamPageCode } from "@/lib/teams";
import { Tooltip } from "./tooltip";

// 實體連結 pattern（UI_UX_SYSTEM §3；UX-ENTITY-LINKS1）：球員/球隊等「實體名」連結
// 走沉穩色 text-ink ＋ 常駐細底線（非色彩單獨可辨識，a11y），hover 才轉 accent。
// 刻意不用 accent 紅——accent 同時是行動色＋數據差(down)色，紅字實體名觀感突兀。
// 「行動連結」（看單場→／導覽／CTA）另保留 accent 紅，不套此 pattern。
export const ENTITY_LINK =
  "text-ink underline decoration-line decoration-1 underline-offset-2 transition-colors hover:text-accent hover:decoration-accent";

// 字母方塊徽章（單一事實來源）：給定 {color, letter} 渲染隊色底＋對比字。
// 各處（排行榜/紀錄室/球員頁/球隊頁沿革）原本各自手寫此 span，統一由此出。
export function LetterBadge({ meta, size = 16, round = false }: { meta: { color: string; letter: string }; size?: number; round?: boolean }) {
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center font-extrabold leading-none"
      style={{ width: size, height: size, borderRadius: round ? size / 2 : Math.max(3, size * 0.22), background: meta.color, color: contrastText(meta.color), fontSize: size * 0.56 }}
    >
      {meta.letter}
    </span>
  );
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

// 小標籤：現役（綠）／已解散（灰）等狀態 pill。
export function Pill({ children, tone = "muted", className = "" }: { children: React.ReactNode; tone?: "up" | "muted"; className?: string }) {
  const cls = tone === "up" ? "bg-up/15 text-up" : "bg-surface-2 text-muted";
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls} ${className}`}>{children}</span>;
}
export const ActivePill = ({ className = "" }: { className?: string }) => <Pill tone="up" className={className}>現役</Pill>;
export const GonePill = ({ className = "" }: { className?: string }) => <Pill tone="muted" className={className}>已解散</Pill>;

// 隊伍徽章：隊色圓角方塊 + 字母（避免官方 logo 版權）。
// 優先用隊名解析(nameMeta，含歷史/已解散隊 era 色)，未知再退回代碼解析。
// decorative：徽章旁已顯示隊名時（NameTag/TeamBadge）設 true → aria-hidden，避免
// 螢幕閱讀器重複念「隊徽 味全龍」。獨立使用（如對戰矩陣表頭僅徽章）則保留 aria-label。
export function TeamLogo({ code, name, size = 24, decorative = false }: { code?: string | null; name?: string | null; size?: number; decorative?: boolean }) {
  const m = name ? nameMeta(name) : null;
  const known = m && m.letter !== "?";
  const bg = known ? m.color : teamColor(code);
  const letter = known ? m.letter : teamLetter(code);
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-md font-extrabold leading-none"
      style={{ width: size, height: size, background: bg, color: contrastText(bg), fontSize: size * 0.56 }}
      aria-label={decorative ? undefined : `${name ?? code ?? ""}隊徽`}
      aria-hidden={decorative || undefined}
    >
      {letter}
    </span>
  );
}

// 卡殼單一事實來源（.card＝surface 底 + border-line + rounded-xl + 微陰影）。
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
export function TeamBadge({ code, name, size = 20, link = false }: { code?: string | null; name?: string | null; size?: number; link?: boolean }) {
  const href = link && isCurrentTeam(code) ? `/teams/${teamPageCode(code)}` : null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <TeamLogo code={code} name={name} size={size} decorative={!!name} />
      {name && (href ? <Link href={href} className={ENTITY_LINK}>{name}</Link> : <span>{name}</span>)}
    </span>
  );
}

// 區塊小標（eyebrow）：每個區塊回答一個問題，配此小標點題（原則 1/5）。
export function Eyebrow({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`text-[11px] font-semibold uppercase tracking-wider text-faint ${className}`}>{children}</div>;
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
        <div key={i} className="rounded-lg bg-surface-2 px-3 py-2 text-center">
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
// - `layout="stack"`（即將挑戰的紀錄專用）：項目名／球員名／錨點／明細**垂直
//   四層**，不靠字級微差區分（全部落在 xs/sm/base 三級）。改版型不是為了省
//   空間（stack 版每卡反而更高，見下方 grep 得到的卡面 log）——是因為
//   row 版在窄欄位下即使兩行也裝不下全聯盟最壞字寬組合（見下）。
//
// **為什麼要垂直堆疊、不是靠加寬欄位或縮字**：需求方 2026-07-28 用 canvas 實測
// 全聯盟最壞值——最長球員名 112px（`伊斯坦大．比力安`／`田中怜利ハモンド`）、
// 最長項目名 88px（`生涯投球局數`）、最長錨點 66px（`連續 5 場`）。半寬左欄
// 3 欄實得寬度僅 ~165px（含內距）：row 版單行需 298px、兩行版需 186px，兩者
// 在 165px 都會斷字；stack 版（每層獨占一行，欄寬只需容納單一元素+內距）僅需
// 136px，165px 尚有 29px 餘裕。這同時修掉一個現存的潛在斷字（見卡面 log：
// 現行 2 欄每格 252px 但單行最壞需 298px，今天沒炸只是運氣，剛好没配到最長
// 名字＋最長項目的組合）。
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
        <div className="text-xs text-muted">{props.label}</div>
        <div className="mt-0.5 text-sm text-ink">{props.name}</div>
        <div className="mt-1 text-base font-bold tabular-nums text-accent">{props.anchor}</div>
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

// RecordCard 清單的共用網格斷點：橫向排列縮短整頁捲動（需求方 2026-07-28 明訂
// 「卡片是希望橫向排列 讓這頁資訊能不用卷軸」）。與 page.tsx「戰績分項」網格
// 同一組斷點，同一頁同樣「把多張小卡片橫向塞進去縮短捲動」的目的不另訂一套。
// gap-2（非其他網格常用的 gap-3）是唯一刻意偏離：RecordCard 內距已較緊湊
// （px-3 py-2.5，非 Card 的 p-4），沿用 gap-3 視覺上會顯得鬆散不成套。
//
// `lg:grid-cols-3` 是**viewport 斷點，不是容器斷點**——只在「這份清單佔滿頁面
// 全寬」的前提下 3 欄才有實得寬度。半寬欄位（如「即將挑戰的紀錄」現在永遠
// 位於 focus-section.tsx 的半寬左欄）viewport lg 仍會觸發、每卡實得寬度只剩
// 一半（1440 實測 546px 卡寬 ÷3≈165px）——這曾是兩輪真實 bug 的成因：
//   1. 第一輪退回：row 版錨點 shrink-0 nowrap 擠壓 headline，逐字斷行。
//   2. 第二輪一度改用 2 欄暫時避開，但那只是「降欄數換寬度」的權宜——本質
//      問題（欄寬 vs. 文字最壞寬度）沒解，只是把門檻從「單行 298px」降到
//      「兩行 186px」，仍未低於 165px 的真實欄寬（差 21px，見上方 RecordCard
//      docstring 的 canvas 實測）。
// 現在 `layout="stack"` 把單卡最壞需求壓到 136px（< 165px），3 欄本身重新
// 安全，故「即將挑戰的紀錄」與「近期球員熱區」統一用回這一個 `RECORD_GRID`
// （不再需要曾經存在的 `RECORD_GRID_2COL` 過渡版本，已移除）。
export const RECORD_GRID = "grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3";

export function SectionHeading({ children, caption }: { children: ReactNode; caption?: ReactNode }) {
  return (
    <div className="mb-1">
      <div className="text-xs font-semibold text-muted">{children}</div>
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
    <div className={`overflow-hidden rounded-xl border border-line ${className}`} aria-hidden>
      <div className="flex gap-3 bg-surface-2 px-3 py-2.5">
        {Array.from({ length: cols }).map((_, i) => <Skeleton key={i} className="h-4 flex-1" />)}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3 border-t border-line px-3 py-2.5">
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
  return <p className={`py-8 text-center text-sm text-accent ${className}`}>{children}</p>;
}

// 場次狀態徽章：全站唯一狀態語彙。done＝完賽（中性）／warn＝延賽·保留（amber 警示）／
// live＝進行中（accent）／scheduled＝未開打（accent 淡）。走語意 token，不用 Tailwind amber-數字。
export type StatusTone = "done" | "warn" | "live" | "scheduled";
const STATUS_TONE_CLS: Record<StatusTone, { solid: string; bare: string }> = {
  done: { solid: "bg-surface-2 text-faint", bare: "text-faint" },
  warn: { solid: "bg-amber/15 text-amber", bare: "text-amber" },
  live: { solid: "bg-accent/15 text-accent", bare: "text-accent" },
  scheduled: { solid: "bg-accent/10 text-accent", bare: "text-accent/80" },
};
// variant solid＝實心 pill（列表）；bare＝純色文字（月曆格等窄空間）。兩型共用 tone→色。
export function StatusBadge({ children, tone, variant = "solid", className = "" }: {
  children: React.ReactNode; tone: StatusTone; variant?: "solid" | "bare"; className?: string;
}) {
  const t = STATUS_TONE_CLS[tone];
  return variant === "bare"
    ? <span className={`font-semibold leading-none ${t.bare} ${className}`}>{children}</span>
    : <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold leading-none ${t.solid} ${className}`}>{children}</span>;
}

// 提示橫幅（warn＝amber 警示，如延賽/保留說明）。走語意 token。
export function Notice({ tone = "warn", icon, children, className = "" }: {
  tone?: "warn"; icon?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  const cls = tone === "warn" ? "border-amber/40 bg-amber/10 text-amber" : "border-line bg-surface-2 text-muted";
  return (
    <div className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm ${cls} ${className}`}>
      {icon != null && <span>{icon}</span>}
      <span className="font-medium">{children}</span>
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

export function PercentileBar({ name, value, pr, def }: { name: string; value: string; pr: number; def?: string }) {
  // 定義提示走共用 Tooltip（原生 title 有延遲且觸控無效）
  const label = <span className="w-16 shrink-0 truncate text-muted">{name}</span>;
  return (
    <div className="flex items-center gap-2 text-xs">
      {def ? <Tooltip content={def}>{label}</Tooltip> : label}
      <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full" style={{ width: `${pr}%`, background: prColor(pr) }} />
      </div>
      <span className="w-11 shrink-0 text-right font-mono tabular-nums text-ink">{value}</span>
      <span className="w-6 shrink-0 text-right font-mono text-faint">{pr}</span>
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
