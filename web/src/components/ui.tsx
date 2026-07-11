import Link from "next/link";
import { contrastText, eraBadge, nameMeta, teamColor, teamLetter } from "@/lib/teams";
import { Tooltip } from "./tooltip";

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
export function NameTag({ name, size = 16 }: { name?: string | null; size?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <TeamLogo name={name} size={size} decorative />
      <span>{name || "—"}</span>
    </span>
  );
}

// 球員連結（無 player_id 時退化為純文字）。
export function PlayerLink({ pid, name, className = "text-accent hover:underline" }: { pid?: string | null; name: string; className?: string }) {
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

export function StatTile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="card px-3 py-2.5 text-center">
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`mt-0.5 font-mono text-lg tabular-nums ${accent ? "text-accent" : "text-ink"}`}>{value}</div>
    </div>
  );
}

export function TeamBadge({ code, name, size = 20 }: { code?: string | null; name?: string | null; size?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <TeamLogo code={code} name={name} size={size} decorative={!!name} />
      {name && <span>{name}</span>}
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
  return (
    <div className="flex items-center gap-2 text-xs">
      <span title={def} className={`w-16 shrink-0 truncate text-muted ${def ? "cursor-help" : ""}`}>{name}</span>
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
