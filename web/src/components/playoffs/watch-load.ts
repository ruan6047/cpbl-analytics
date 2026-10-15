// #300 S08c：4A 懶人包的「連投摘要」純函式（天數＋期間球數＋期間局數）。
//
// 紅線：
// - 天數與球數照後端 `load.metrics`（C＝截至 D−1 的連續登板日數；P1／S2／S3＝C 為 1／2／3 時的期間球數），
//   這裡只選欄位，⛔ 不重算、⛔ 不寫任何門檻常數。
// - 局數後端沒有直接欄位，只能由 `recent[]`（最近 3 筆登板）推導，且必須 fail-closed：
//   每個連投日在 `recent[]` 裡日期可信的筆數要剛好等於該日 `appearances`，且每筆 `outs` 非 null；
//   任一不成立 ⇒ 局數未知並給原因。⛔ 缺筆或 null 當 0。
// - 灰色（C＝null）不給任何數字。
import type { LoadDay, WatchPitcher } from "@/lib/playoffs-watch";

export type StreakInnings =
  | { known: true; outs: number; ip: string }
  | { known: false; reason: string };

export type Streak =
  | { kind: "unknown" }
  | { kind: "none" }
  | { kind: "streak"; days: number; atLeast: boolean; pitches: number | null; innings: StreakInnings };

/** outs → 「2.1」（棒球局數記法）。 */
export function outsToIp(outs: number): string {
  return `${Math.floor(outs / 3)}.${outs % 3}`;
}

/** 連投期間局數：連投日＝offset 1…n（n＝C，`c_at_least` 時 n＝3）。 */
export function streakInnings(p: WatchPitcher, n: number): StreakInnings {
  let outs = 0;
  for (let k = 1; k <= n; k++) {
    const day: LoadDay | undefined = p.load.days.find((d) => d.offset === k);
    if (!day || !day.complete || day.appearances < 1) {
      return { known: false, reason: "連投日的逐日資料不完整，無法加總局數" };
    }
    const rows = p.recent.filter((a) => a.date_trusted && a.date === day.date);
    if (rows.length !== day.appearances) {
      return { known: false, reason: `最近登板清單只含 ${p.recent.length} 筆，無法涵蓋全部連投日的登板` };
    }
    for (const a of rows) {
      if (a.outs == null) return { known: false, reason: "連投期間有場次缺局數" };
      outs += a.outs;
    }
  }
  return { known: true, outs, ip: outsToIp(outs) };
}

export function streakOf(p: WatchPitcher): Streak {
  const c = p.load.metrics.C;
  if (c == null) return { kind: "unknown" };
  if (c === 0) return { kind: "none" };
  const n = p.load.c_at_least ? 3 : Math.min(c, 3);
  const pitches = n === 1 ? p.load.metrics.P1 : n === 2 ? p.load.metrics.S2 : p.load.metrics.S3;
  return { kind: "streak", days: n, atLeast: p.load.c_at_least, pitches, innings: streakInnings(p, n) };
}

/** 可見摘要：「連投 2 天・26 球・2.0 局」。 */
export function streakText(s: Streak): string {
  switch (s.kind) {
    case "unknown": return "連投 ?";
    case "none": return "昨日未登板";
    case "streak": {
      const ip = s.innings.known ? `${s.innings.ip} 局` : "? 局";
      const pitches = `${s.pitches ?? "?"} 球`;
      return s.atLeast ? `連投 3+ 天・近 3 日 ${pitches}・${ip}` : `連投 ${s.days} 天・${pitches}・${ip}`;
    }
  }
}

/** 單日格的球數字：完整日照實；不完整日有已知球數寫「N+?」，沒有寫「?」（⛔ 畫成 0）。 */
export function dayPitchesText(d: LoadDay): string {
  if (d.complete) return String(d.pitches);
  return d.pitches > 0 ? `${d.pitches}+?` : "?";
}
