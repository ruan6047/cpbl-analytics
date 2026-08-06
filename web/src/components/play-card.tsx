"use client";

// 打席卡 [plate appearance card]：**關鍵打席與逐打席共用的唯一呈現形式**
//（UI_UX_SYSTEM §10.4 registry：同一概念一個 owner）。
//
// 需求方 2026-08-06 上線首日回饋（UX-GAME-PA1）：「逐打席有辦法用類似關鍵打席的 UI 嗎，
// 把它弄成一個元件。兩者差別是逐打席有折疊區來詳細記錄該打席的每顆球，應該差不多。
// 關鍵打席有一個逐打席缺少的狀態，就是該打席的壘包狀態跟即時勝率。」
//
// 版式（三排，兩變體共用；沿生產「關鍵時刻」卡骨架）：
//   上排：局面脈絡（局數／壘包圖／出局／分差）＋**置右獨立**的受益隊勝率標示
//   中排：打者 · 官方結果 · 投手（＋得分 chip、ΔRE24 chip）
//   下排：雙色勝率條（打席後水平＋受益隊輔助色位移段）
//   折疊區（`pbp` 變體）：該打席的每顆球，由呼叫端以 children 傳入，**展開才渲染**
//
// 兩變體的差異只有互動與折疊，不是兩套視覺：
//   * `key`（關鍵打席）：整張卡是跳轉按鈕，無折疊、無選中態。
//   * `pbp`（逐打席）：卡頭是折疊開關（`aria-expanded`），有選中態 ring，展開後接逐球列。
//
// 手機優先（375px 為設計基準，本卡第一驗收準則）：上排允許換行（`flex-wrap`）且勝率標示
// `shrink-0` 永不被擠壓；桌面寬度下不觸發換行，故關鍵打席的既有視覺零回歸。

import type { ReactNode } from "react";
import { PlayerLink } from "@/components/ui";
import { Re24Badge } from "@/components/re24-badge";
import { RunsBadge } from "@/components/runs-badge";
import { WpSwingBadge } from "@/components/wp-swing-badge";
import { WpSwingBar } from "@/components/wp-swing-bar";
import { halfLabel } from "@/lib/game-facts";

/** 該打席的勝率（主隊視角原值；顯示層再夾與轉受益隊）。 */
export type PlayCardWp = {
  before: number | null;
  after: number | null;
  terminal?: boolean;
  delta: number | null;
};

export type PlayCardTeams = {
  homeName?: string | null;
  awayName?: string | null;
  homeColor: string;
  awayColor: string;
};

export type PlayCardProps = {
  variant?: "key" | "pbp";
  /** 上排局面脈絡（打席**前**的狀態）。 */
  inning: number | null;
  half: string | null;
  outsBefore: number | null;
  basesBefore: string[];
  /** 打席前分差文字（如「4–2」「平手」）；空字串＝不顯示。 */
  margin?: string;
  /** 分差 ≥7 的事實旗標（呈現為文字標籤，不降飽和）。 */
  garbageTime?: boolean;
  /** 中排：打者／官方結果／投手。 */
  hitterId?: string | null;
  hitterName: string;
  pitcherName: string;
  resultAction: string | null;
  /** `（5 球）`——逐打席變體的球數標示。 */
  pitchCountLabel?: string | null;
  runs?: number | null;
  scoreAfter?: { away: number; home: number } | null;
  deltaRe24?: number | null;
  wp?: PlayCardWp | null;
  teams: PlayCardTeams;
  /** 整張卡（`key`）或卡頭（`pbp`）的點擊行為；缺席時不可點。 */
  onActivate?: () => void;
  ariaLabel?: string;
  /** `pbp`：是否為當前選中的打席（ring 標示）。 */
  active?: boolean;
  /** `pbp`：折疊區是否展開；展開時才渲染 children（84 列不預先展開所有逐球）。 */
  expanded?: boolean;
  /** `pbp` 折疊區內容（逐球列）。 */
  children?: ReactNode;
};

function BaseDiamond({ bases }: { bases: string[] }) {
  const on = (b: string) => (bases ?? []).includes(b);
  const cell = (filled: boolean) =>
    `inline-block h-2 w-2 rotate-45 border ${filled ? "border-ink bg-ink" : "border-line-strong"}`;
  return (
    <span aria-hidden className="inline-grid grid-cols-3 grid-rows-2 items-center gap-px">
      <span /><span className={cell(on("2"))} /><span />
      <span className={cell(on("3"))} /><span /><span className={cell(on("1"))} />
    </span>
  );
}

/** 折疊指示三角（`pbp` 變體）；純裝飾，狀態由 `aria-expanded` 承載。 */
function Caret({ open }: { open: boolean }) {
  return (
    <span aria-hidden
      className={`inline-block text-[9px] text-faint transition-transform ${open ? "rotate-90" : ""}`}>
      ▶
    </span>
  );
}

export function PlayCard({
  variant = "key", inning, half, outsBefore, basesBefore, margin, garbageTime,
  hitterId, hitterName, pitcherName, resultAction, pitchCountLabel,
  runs, scoreAfter, deltaRe24, wp, teams, onActivate, ariaLabel,
  active = false, expanded = false, children,
}: PlayCardProps) {
  const pbp = variant === "pbp";
  const hasSwing = wp != null && wp.delta !== null && wp.delta !== undefined;

  const head = (
    <>
      {/* 上排：局面脈絡（左，可換行）＋受益隊勝率（右，不被擠壓） */}
      <div className="flex items-baseline justify-between gap-2">
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs font-medium text-muted">
          {pbp && <Caret open={expanded} />}
          {inning}{halfLabel(half)}
          <BaseDiamond bases={basesBefore} />
          <span className="text-faint">{outsBefore ?? "—"} 出局</span>
          {margin && <span className="text-faint">{margin}</span>}
          {garbageTime && (
            <span className="rounded bg-surface-2 px-1 py-px text-[10px] text-muted">分差 ≥7</span>
          )}
        </span>
        {hasSwing && (
          <WpSwingBadge value={wp!.delta} homeName={teams.homeName} awayName={teams.awayName}
            homeColor={teams.homeColor} awayColor={teams.awayColor} />
        )}
      </div>
      {/* 中排：打者 · 結果 · 投手（＋得分／ΔRE24 chips） */}
      <div className="mt-0.5 text-sm text-ink">
        <PlayerLink pid={hitterId ?? undefined} name={hitterName} />
        {pitchCountLabel && (
          <span className="ml-1 text-[10px] font-semibold text-muted">{pitchCountLabel}</span>
        )}
        <span className="mx-1 text-faint">·</span>
        {(resultAction ?? "").trim()}
        {pitcherName && <span className="ml-1.5 text-xs text-faint">投：{pitcherName}</span>}
        <RunsBadge runs={runs} {...(scoreAfter ?? {})} />
        {/* ΔRE24 缺值時整個 chip 不出現（非打席的佈局列、來源修正待對帳…）：
            「ΔRE24 —」對讀者沒有資訊，只是佔位。關鍵打席一律有值，故不受影響。 */}
        {deltaRe24 !== null && deltaRe24 !== undefined && (
          <Re24Badge value={deltaRe24} muted={hasSwing} />
        )}
      </div>
      {/* 下排：雙色勝率條 */}
      {hasSwing && (
        <WpSwingBar before={wp!.before} after={wp!.after} terminal={wp!.terminal}
          homeColor={teams.homeColor} awayColor={teams.awayColor}
          homeName={teams.homeName} awayName={teams.awayName} />
      )}
    </>
  );

  const padding = "rounded-lg px-2.5 py-2 text-left";
  if (!pbp) {
    return onActivate ? (
      <button type="button" aria-label={ariaLabel} onClick={onActivate}
        className={`block w-full ${padding} transition-colors hover:bg-surface-2`}>
        {head}
      </button>
    ) : (
      <div aria-label={ariaLabel} className={padding}>{head}</div>
    );
  }

  // 選中態走**中性強調**（`surface-2` 底 + `line-strong` 描邊），不用 accent 淡底：
  // accent 在本站語意是得分／負向刻度（`up` 藍 `down` 紅），拿紅色系當「選取」語意錯位，
  // 需求方看到的也是「整片淡紅色很奇怪」。中性 token 在深色模式自動適配。
  return (
    <div className={`rounded-lg ${active ? "bg-surface-2 ring-1 ring-line-strong" : ""}`}>
      <button type="button" aria-label={ariaLabel} aria-expanded={expanded} onClick={onActivate}
        className={`block w-full scroll-mt-16 ${padding} transition-colors ${
          active ? "" : "hover:bg-surface-2"}`}>
        {head}
      </button>
      {/* 展開區＝**卡的延伸，不是新容器**：只用一條分隔線 + 縮排表達層級，不加圓角框
          （需求方：「詳細內容又用一個圓角淺紅框線呈現，看起來有點雜」）。
          一張卡最多一層邊界——邊界由選中態的 ring 承擔，展開區不再自帶。
          展開才渲染逐球列：收合的打席不產生任何 DOM（長半局的手機效能）。 */}
      {expanded && children ? (
        <div className="ml-2.5 mr-2 border-t border-line pb-1.5 pt-1">{children}</div>
      ) : null}
    </div>
  );
}
