// `/playoffs` 全頁頁尾說明（#285 續做 WP2；MOUNT-CONTRACT r3 §2.4、§2.5）。
//
// 需求方裁定（#281 6194693029，本卡登記 6194706200）：各區的說明性注意事項一律放頁尾小字；缺值格只留簡短狀態；
// 頁尾掛點與彙整歸 #285。兩個來源：
// 1. 已登記的區：registry 的 `notes(data)`，以「該區畫面上正在顯示的那份資料」呼叫（未載入或無上一份 ⇒ null）。
// 2. `PAGE_NOTES`：第 1、4 區與沒有區塊的卡的固定說明，由 #285 寫入。G1 前為空（契約 §10 後續增量）。
//
// 規則：依 C2 區序（series → watch → roster → teams）排、同區內照回傳順序；同 key 只留第一次出現處；
// 同 key 不同文字取第一條並在開發環境 warn；合計 0 條 ⇒ 頁尾整區不渲染。⛔ 截斷、⛔ 摺疊、⛔ 解讀他卡 payload。

import { PLAYOFFS_AREA_ORDER, type PlayoffsAreaId } from "./playoffs-areas.ts";
import type { WatchState } from "./playoffs-poll.ts";

export type PlayoffsNote = {
  /** 全域唯一："<區 id>.<snake_case>"；跨區共用 "common.<snake_case>"。依「同一件事」保持穩定。 */
  key: string;
  /** 純文字；⛔ HTML／Markdown。 */
  text: string;
  /** 選填；url 限官方站 https 或站內相對路徑（`isAllowedSourceUrl`）。 */
  source?: { label: string; url: string };
};

export type AreaNotes = { area: PlayoffsAreaId; notes: readonly PlayoffsNote[] };

/** 第 1、4 區（無 registry 登記）的固定說明。G1 前為空；文字由各卡依契約 §9 交 PM 對齊後寫入。 */
export const PAGE_NOTES: Readonly<Record<"series" | "watch", readonly PlayoffsNote[]>> = { series: [], watch: [] };

export type NoteConflict = { key: string; kept: string; dropped: string };

/** 依 C2 區序合併、同 key 去重（保留第一次出現的位置與文字）。回傳結果與衝突清單。 */
export function mergeNotes(groups: readonly AreaNotes[]): { notes: PlayoffsNote[]; conflicts: NoteConflict[] } {
  const ordered = groups
    .map((g, i) => ({ g, i }))
    .sort((a, b) => PLAYOFFS_AREA_ORDER.indexOf(a.g.area) - PLAYOFFS_AREA_ORDER.indexOf(b.g.area) || a.i - b.i);
  const seen = new Map<string, PlayoffsNote>();
  const out: PlayoffsNote[] = [];
  const conflicts: NoteConflict[] = [];
  for (const { g } of ordered) {
    for (const n of g.notes) {
      const prev = seen.get(n.key);
      if (prev) {
        if (prev.text !== n.text) conflicts.push({ key: n.key, kept: prev.text, dropped: n.text });
        continue;
      }
      seen.set(n.key, n);
      out.push(n);
    }
  }
  return { notes: out, conflicts };
}

/** 開發環境把衝突印出來（正式環境靜默，取第一條）。 */
export function warnNoteConflicts(conflicts: readonly NoteConflict[]): void {
  if (process.env.NODE_ENV === "production") return;
  for (const c of conflicts) console.warn(`[playoffs-notes] key「${c.key}」文字不同，保留第一條：「${c.kept}」，忽略：「${c.dropped}」`);
}

/** 區畫面上正在顯示的那份資料：接受的新資料；stale／error 時是上一份；未載入或無上一份 ⇒ null（契約 §2.5）。 */
export function shownData<A>(state: WatchState<A> | undefined): A | null {
  if (!state || state.kind === "idle") return null;
  return state.kind === "data" ? state.data : state.previous;
}

const OFFICIAL_HOSTS = new Set(["www.cpbl.com.tw", "cpbl.com.tw", "stats.cpbl.com.tw"]);

/** 來源連結只收站內相對路徑或官方站 https 網址；其他一律不渲染成連結。 */
export function isAllowedSourceUrl(url: string): boolean {
  if (url.startsWith("/") && !url.startsWith("//")) return true;
  try {
    const u = new URL(url);
    return u.protocol === "https:" && OFFICIAL_HOSTS.has(u.hostname);
  } catch {
    return false;
  }
}

/** 同 key 不同文字的檢查（測試用）：對已登記區的 `notes(null)` 與 `PAGE_NOTES`。依資料產生者由各卡自測。 */
export function staticNoteConflicts(groups: readonly AreaNotes[]): NoteConflict[] {
  return mergeNotes(groups).conflicts;
}
