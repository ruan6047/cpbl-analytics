// #273：季後賽單場頁與報告內容共用的小工具——季後場次名、報告名稱、單場頁的公告安排、完賽單場頁的報告入口、
// 頁尾時戳。只處理文案與指向，不定義場間報告／觀戰報告的角色（角色定義屬 #278）。
//
// 季後場次的**唯一**叫法（「季後挑戰賽 G4」「台灣大賽 G1」）由本檔提供，避免同一場在各頁各寫一套
// （N31「同一報告三種叫法」）。場序只從兩個既有事實取得：
//   1. 共用旅程模型的公告歸併：slot 已對到資料庫正式列（`slot.row`）→ `slot.seq`；
//   2. 系列完賽場的 `game_no`（postseason-summary，與 game_sno 一起由後端給）。
// 兩者都沒有就回 null，呼叫端退回不含場序的說法。
//
// ⛔ 不從場號（game_sno）推場序：C 場只認「同一天唯一一場 C 公告」，E 場以官方場號＋日期比對。

import type { AnnouncedSlot, PostseasonAnnouncement } from "./postseason-announcement.ts";
import type { PostseasonJourney } from "./postseason-journey.ts";

/** 報告的兩個名稱（N31：全站只用這兩個，不再出現「截至場場間報告」「回顧」）；單場頁入口文字也用（N38）。 */
export const REPORT_NAMES = { between: "場間報告", preview: "觀戰報告" } as const;

/** 「季後挑戰賽 G4」；找不到可核實的場序回 null。 */
export function postseasonGameName(
  j: Pick<PostseasonJourney, "series" | "slots"> | null | undefined,
  kind: string,
  sno: number,
): string | null {
  if (!j || (kind !== "E" && kind !== "C")) return null;
  const series = j.series[kind];
  const slot = j.slots.find((s) => s.kind === kind && s.row?.game_sno === sno);
  if (slot) return `${series.name} G${slot.seq}`;
  const game = series.games.find((g) => g.game_sno === sno);
  return game ? `${series.name} G${game.game_no}` : null;
}

/** 旅程模型的下一場名稱；公告場也有場序，故不要求已入庫。 */
export function nextGameName(j: Pick<PostseasonJourney, "series" | "next"> | null | undefined): string | null {
  const s = j?.next;
  return s ? `${j!.series[s.kind].name} G${s.seq}` : null;
}

/** `YYYY-MM-DD` → `10/12`。 */
export function monthDay(ymd: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(ymd);
  return m ? `${Number(m[1])}/${m[2]}` : ymd;
}

/** ISO 時戳 → 「2026-10-14 14:35（台北）」：讀者不需要微秒與 UTC 偏移（N08）。無法解析時原樣回傳。 */
export function taipeiMinute(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  const text = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(ms);
  return `${text}（台北）`;
}

/** 單場頁沒有旅程模型時，以官方公告找出這一場的公告安排（開賽時刻、場序、如有必要）。
 *  比對沿用旅程模型的規則：E 以官方場號＋日期；C 沒有官方場號，只認「同一天唯一一場 C 公告」。
 *  ⛔ 不以場號猜場序；日期對不上或同日不唯一就回 null。 */
export function announcedSlotOf(
  ann: Pick<PostseasonAnnouncement, "slots"> | null | undefined,
  kind: string,
  sno: number,
  date: string,
): AnnouncedSlot | null {
  if (!ann || !date) return null;
  const sameDay = ann.slots.filter((s) => s.kind === kind && s.date === date);
  if (kind === "E") return sameDay.find((s) => s.officialSno === sno) ?? null;
  return kind === "C" && sameDay.length === 1 ? sameDay[0] : null;
}

/** #273 N38：完賽單場頁的報告入口。下一場目標（`/preview-target`）還在解析時回 pending，
 *  呼叫端只留同高空位；解析後一次定案——有可靠下一場連觀戰報告，否則（含失敗）連本場場間報告。
 *  `previewHref`：undefined＝解析中、null＝沒有可靠下一場。 */
export function reportEntry(input: {
  recapHref: string | null; backendFinal: boolean; kind: string; year: number | undefined; previewHref: string | null | undefined;
}): { pending: true } | { pending: false; href: string; text: string } | null {
  const { recapHref, backendFinal, kind, year, previewHref } = input;
  if (!recapHref) return null;
  if (backendFinal && !!year && (kind === "E" || kind === "C") && previewHref === undefined) return { pending: true };
  return previewHref
    ? { pending: false, href: previewHref, text: "下一場詳情" }
    : { pending: false, href: recapHref, text: "本場詳情" };
}
