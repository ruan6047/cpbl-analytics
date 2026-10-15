// 連續紀錄口語化（球隊頁與季後賽第 2 區共用；#287 自 `app/teams/[code]/page.tsx` 抽出，行為不變）。

/** 官方 streak「勝2／敗3／和1」→ 口語「二連勝／三連敗」；單場不用「連」（避免「一連敗」）。 */
export const streakZh = (s?: string | null): string => {
  if (!s) return "—";
  const m = s.match(/^(勝|敗|負|和)\s*(\d+)$/);
  if (!m) return s;
  const n = parseInt(m[2], 10);
  if (!n) return s;
  const res = m[1] === "負" ? "敗" : m[1];
  if (n === 1) return `1${res}`;
  const cjk = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  const numZh = (x: number): string =>
    x <= 10 ? cjk[x] : x < 20 ? `十${cjk[x - 10]}` : `${cjk[Math.floor(x / 10)]}十${x % 10 ? cjk[x % 10] : ""}`;
  return `${numZh(n)}連${res}`;
};

export type StreakFact = { result: "W" | "L" | "T"; len: number; through: string };

const RESULT_ZH: Record<StreakFact["result"], string> = { W: "勝", L: "敗", T: "和" };

/** 後端結尾連續段 {result, len} → 與球隊頁同一口語（`streakZh`）；無資料回 "—"。 */
export const streakLabel = (s?: StreakFact | null): string =>
  s ? streakZh(`${RESULT_ZH[s.result]}${s.len}`) : "—";
