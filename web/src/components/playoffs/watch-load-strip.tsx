import type { ReactNode } from "react";

import { Tooltip } from "@/components/tooltip";
import {
  LEVEL_TEXT,
  LEVEL_TONE,
  appearanceText,
  offsetLabel,
  pitcherRoles,
  shortDate,
  triggerText,
  type WatchPitcher,
} from "@/lib/playoffs-watch";
import { dayPitchesText, streakOf, streakText } from "./watch-load";

// #300 S08c：4A 每位投手的「燈號＋4 格球數日條＋連投摘要」（懶人包式呈現）。
//
// 只換層不刪內容（需求方原話「需要修改的不是內容 而是呈現方式」）：#289 版每一行說明仍在，
// 搬進共用 `Tooltip`（桌機移入、觸控點一下、點別處／Escape 收起）。本檔維持 server-safe，
// 互動只來自既有 client 島 `Tooltip`。
// - 長條只是輔助編碼，數字一律寫出；比例尺＝整個 4A 已知單日球數最大值，⛔ 不寫門檻常數。
// - 長條用中性色（`bg-muted`），燈號色只在燈號點，避免暗示「某一天是紅」。
// - 不完整日：虛線框＋「?」或「N+?」，⛔ 畫成 0 或空白。
// - 展示項目依需求方逐項裁定（#300 6191101762，PLAN-r2 §16）：日條提示移除逐日球數（E14，保留賽句保留）、
//   連續登板 C 日・今日 Q 次（E16）、連投時成績 ERA（E19）、逐人當場登錄（E20）；日條標籤改白話（E8）。

/** 日條標籤（E8）：「D−3」是內部術語，畫面改白話；offset 超出 0–3 時退回 `offsetLabel`。 */
const DAY_LABEL: Record<number, string> = { 3: "3 天前", 2: "前天", 1: "昨天", 0: "今日" };
export function dayLabel(offset: number): string {
  return DAY_LABEL[offset] ?? offsetLabel(offset);
}

/** 燈號提示內容：觸發理由、灰色的缺資料理由；沒有可說明的內容回 null（燈號不成為按鈕）。 */
export function levelDetail(p: WatchPitcher): ReactNode | null {
  const { load } = p;
  if (load.triggers.length) return <p>{load.triggers.map(triggerText).join("、")}</p>;
  if (load.level === "unknown" && load.incomplete.length) {
    return <p>資料不完整：{load.incomplete.map((i) => `${shortDate(i.date)} ${i.text.join("、")}`).join("；")}</p>;
  }
  return null;
}

/** 日條提示內容：完整休息、連投局數無法判定原因、保留賽球數、最近登板（其餘 #289 項目依 §16 裁定移除）。 */
export function loadDetail(p: WatchPitcher): ReactNode {
  const { load } = p;
  const streak = streakOf(p);
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
      <dt className="opacity-75">完整休息</dt>
      <dd>
        {load.full_rest_days != null ? `${load.full_rest_days} 天（最後投球 ${shortDate(load.last_pitch_date)}）`
          : load.rest_unknown_reason ? "無法判定（近期資料不完整）" : "本季無投球紀錄"}
      </dd>
      {streak.kind === "streak" && !streak.innings.known ? (
        <>
          <dt className="opacity-75">連投局數</dt>
          <dd>無法判定：{streak.innings.reason}</dd>
        </>
      ) : null}
      {load.unattributed.length ? (
        <>
          <dt className="opacity-75">保留賽</dt>
          <dd>另有保留賽 {load.unattributed.map((u) => u.pitches ?? "?").join("、")} 球日期未定</dd>
        </>
      ) : null}
      <dt className="opacity-75">最近登板</dt>
      <dd>{p.recent.length ? p.recent.map(appearanceText).join("；") : "本季無登板紀錄"}</dd>
    </dl>
  );
}

function Lamp({ p }: { p: WatchPitcher }) {
  const { load } = p;
  const tone = LEVEL_TONE[load.level];
  const gap = load.level === "unknown" && load.incomplete.length > 0;
  const face = (
    <>
      <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-full ${tone.dot}`} />
      {LEVEL_TEXT[load.level]}
      {gap ? <span className="rounded border border-dashed border-line-strong px-1 text-xs font-normal text-muted">資料不完整</span> : null}
    </>
  );
  const detail = levelDetail(p);
  if (detail == null) {
    return <span data-lamp className={`inline-flex items-center gap-1 font-bold ${tone.text}`}>{face}</span>;
  }
  return (
    <Tooltip content={detail} suppressUnderline>
      <button type="button" data-lamp aria-label={`${LEVEL_TEXT[load.level]}${gap ? "，資料不完整" : ""}：顯示理由`}
        className={`relative inline-flex min-h-6 touch-manipulation items-center gap-1 rounded font-bold ${tone.text} before:absolute before:-inset-x-1 before:-inset-y-2.5 before:content-[''] hover:bg-surface-2`}>
        {face}
      </button>
    </Tooltip>
  );
}

/** 每位投手一列：名字＋角色籤＋燈號（左）＋ 4 格球數日條＋連投摘要（右），緊湊表列排法。 */
export function PitcherLoadRow({ p, scaleMax }: { p: WatchPitcher; scaleMax: number }) {
  const { load } = p;
  const days = [...load.days].sort((a, b) => b.offset - a.offset);
  const streak = streakOf(p);
  const summary = streakText(streak);
  const roles = pitcherRoles(p);
  const spoken = days.map((d) => `${dayLabel(d.offset)} ${shortDate(d.date)} ${d.complete ? `${d.pitches} 球` : d.pitches > 0 ? `已知 ${d.pitches} 球，另有未知` : "未知"}`);
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 py-1.5 text-sm" data-level={load.level}>
      <div className="flex min-w-[9rem] flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className="font-bold text-ink">{p.name ?? p.player_id}</span>
        {roles.length ? roles.map((role) => (
          <span key={role} data-role className="pm-tag">#{role}</span>
        )) : <span className="text-[11px] text-faint">角色未標記</span>}
        <Lamp p={p} />
        {load.live ? <span className="pm-st pm-st--live">即時</span> : null}
      </div>
      <Tooltip content={loadDetail(p)} suppressUnderline>
        <button type="button" data-strip
          aria-label={`近 4 日球數：${spoken.join("、")}${load.unattributed.length ? "；另有保留賽球數日期未定" : ""}；${summary}；顯示詳情`}
          className="flex min-h-9 touch-manipulation flex-wrap items-center gap-x-2.5 gap-y-1 rounded px-1.5 py-0.5 text-left hover:bg-surface-2">
          <span className="flex items-end gap-1" aria-hidden>
            {days.map((d) => {
              const pct = scaleMax > 0 ? Math.round((Math.max(d.pitches, 0) / scaleMax) * 100) : 0;
              return (
                <span key={d.date} data-day={d.offset} data-complete={d.complete ? "1" : "0"} className="flex w-7 flex-col items-center">
                  <span className={`text-[11px] leading-4 tabular-nums ${d.complete ? "text-ink" : "text-muted"}`}>{dayPitchesText(d)}</span>
                  <span className={`relative h-6 w-full overflow-hidden rounded-sm border bg-surface-2 ${d.complete ? "border-line" : "border-dashed border-line-strong"}`}>
                    {pct > 0 ? <span className="absolute inset-x-0 bottom-0 bg-muted" style={{ height: `${pct}%` }} /> : null}
                  </span>
                  <span className="text-[11px] text-muted">{dayLabel(d.offset)}</span>
                </span>
              );
            })}
            {load.unattributed.length ? (
              <span data-unattributed className="self-center rounded border border-dashed border-line-strong px-1 text-[11px] text-muted">保留賽 +?</span>
            ) : null}
          </span>
          <span data-streak={streak.kind} className={`text-xs font-bold ${streak.kind === "streak" ? "text-ink" : "text-muted"}`}>{summary}</span>
        </button>
      </Tooltip>
    </li>
  );
}
