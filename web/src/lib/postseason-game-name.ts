// #273：季後賽單場頁與報告內容共用的小工具——報告名稱、單場頁的公告安排、完賽單場頁的報告入口、
// 頁尾時戳。只處理文案與指向，不定義場間報告／觀戰報告的角色（角色定義屬 #278）。
//
// ⛔ 不從場號（game_sno）推場序：C 場只認「同一天唯一一場 C 公告」，E 場以官方場號＋日期比對。

import type { AnnouncedSlot, PostseasonAnnouncement } from "./postseason-announcement.ts";

/** 報告的兩個名稱：單場頁入口文字用（N38）。 */
export const REPORT_NAMES = { between: "場間報告", preview: "觀戰報告" } as const;

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
    ? { pending: false, href: previewHref, text: `下一場${REPORT_NAMES.preview}` }
    : { pending: false, href: recapHref, text: `${REPORT_NAMES.between}：下一場兩隊背景` };
}
