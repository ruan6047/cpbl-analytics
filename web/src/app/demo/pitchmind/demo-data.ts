// PitchMind 示意頁：**完整合成的示意資料與比賽流程劇本**（#452 修正三）。
//
// 全部為合成示意：球員匿名（打者 A、投手 B…），不對應任何真實球員或比賽，也不取自
// ~/Dev/Rebas 研究檔或本站正式資料。參考線與各來源數字都是直接寫好的模擬值，不是模型輸出。
// 正式資料要另建資料檔並在 view 層換 import；⛔ 不要把正式資料寫進本檔。只討論壘上無人。
//
// 劇本（以「外角高速球」為主線；打者 A 的示意指標 62 → 74 → 82 → 70 → 82）：
//   打者 A 上場（距離尚遠）→ 未出棒（接近區內）→ 界外（已超過）→ 追打揮空（回落）→
//   一顆不符合條件的球 → 2-2 變 3-2（參考線隨情境改變）→ 打席結束、打者 C 帶入自己的資料 →
//   打者 C 的符合／不符合條件來球與回落。

import type {
  BaselineEntry, BaselineTable, CountKey, CountTable, GameEvent, HLoc, Outcome, PitchEvent, ReferenceTable,
  Situation, VLoc, ZoneResult,
} from "./model.ts";

/** 內部判定「樣本不足」用的暫定值；畫面不顯示此數字，實際門檻待研究。 */
export const DEMO_MIN_N = 10;

const EMPTY = { first: false, second: false, third: false };
const sit = (inning: number, batter: string, outs: number, balls = 0, strikes = 0): Situation => ({
  inning, half: "top", batter, batterHand: "R", pitcher: "投手 B", balls, strikes, outs, bases: EMPTY,
});

// 位置 → 示意座標（捕手視角；右打者外角在 +x）。
const X: Record<HLoc, number> = { inside: -0.27, middle: 0.0, outside: 0.27 };
const Y: Record<VLoc, number> = { high: 1.08, mid: 0.76, low: 0.42 };
const SPEED: Record<string, number> = { 速球: 147, 滑球: 132, 變速: 128 };
const ZONE: Record<Outcome, ZoneResult> = { take: "take", whiff: "whiff", foul: "foul", weak: "out", solid: "out", hard: "out" };

type P = {
  seq: number; pitch: string; h: HLoc; v: VLoc; o: Outcome;
  text: string; after: Situation; script?: string; dx?: number; dy?: number; dv?: number;
};
const pitch = (p: P): PitchEvent => ({
  kind: "pitch", id: `ev-${p.seq}`, seq: p.seq, label: `全場第 ${p.seq} 球`,
  pitch: p.pitch, h: p.h, v: p.v, x: X[p.h] + (p.dx ?? 0), y: Y[p.v] + (p.dy ?? 0),
  speed: (SPEED[p.pitch] ?? 140) + (p.dv ?? 0),
  outcome: p.o, zoneResult: ZONE[p.o], resultText: p.text, after: p.after, script: p.script,
});
const paStart = (id: string, label: string, after: Situation, script?: string): GameEvent =>
  ({ kind: "pa_start", id, label, after, script });

const OH = { pitch: "速球", h: "outside", v: "high" } as const;
const OL = { pitch: "滑球", h: "outside", v: "low" } as const;

/**
 * 事件序列。展演從 REPLAY_START（6 局上打者 A 上場）開始；之前的事件是載入時已發生的本場資料
 * （只列與打者 A、C、D 有關的球），所以打者上場時就帶著他本場先前打席的觀察。
 */
export const DEMO_EVENTS: GameEvent[] = [
  // ── 1 局上 ──
  paStart("pa-1a", "1 局上・打者 A 上場", sit(1, "打者 A", 0)),
  pitch({ seq: 1, ...OH, o: "take", text: "壞球", dx: 0.06, after: sit(1, "打者 A", 0, 1, 0) }),
  pitch({ seq: 2, ...OH, o: "foul", text: "界外", after: sit(1, "打者 A", 0, 1, 1) }),
  pitch({ seq: 3, ...OL, o: "foul", text: "界外", after: sit(1, "打者 A", 0, 1, 2) }),
  pitch({ seq: 4, ...OH, o: "foul", text: "界外", dv: -1, after: sit(1, "打者 A", 0, 1, 2) }),
  pitch({ seq: 5, pitch: "變速", h: "middle", v: "low", o: "whiff", text: "揮空三振", after: sit(1, "打者 C", 1) }),
  pitch({ seq: 6, ...OH, o: "take", text: "好球（未揮）", dx: -0.05, dy: -0.06, after: sit(1, "打者 C", 1, 0, 1) }),
  pitch({ seq: 7, ...OL, o: "foul", text: "界外", after: sit(1, "打者 C", 1, 0, 2) }),
  pitch({ seq: 8, pitch: "速球", h: "inside", v: "mid", o: "solid", text: "中外野飛球出局", after: sit(1, "打者 D", 2) }),
  pitch({ seq: 9, ...OH, o: "solid", text: "右外野飛球出局", dv: 1, after: sit(4, "打者 A", 0) }),
  // ── 4 局上 ──
  pitch({ seq: 41, ...OL, o: "take", text: "壞球", dy: -0.05, after: sit(4, "打者 A", 0, 1, 0) }),
  pitch({ seq: 42, ...OH, o: "take", text: "壞球", dy: 0.07, after: sit(4, "打者 A", 0, 2, 0) }),
  pitch({ seq: 43, ...OH, o: "foul", text: "界外", after: sit(4, "打者 A", 0, 2, 1) }),
  pitch({ seq: 44, ...OH, o: "hard", text: "強勁平飛球被接殺", dx: -0.06, dy: -0.06, after: sit(4, "打者 C", 1) }),
  pitch({ seq: 45, ...OH, o: "take", text: "壞球", dx: 0.07, dv: 1, after: sit(4, "打者 C", 1, 1, 0) }),
  pitch({ seq: 46, ...OL, o: "take", text: "壞球", dy: -0.06, after: sit(4, "打者 C", 1, 2, 0) }),
  pitch({ seq: 47, pitch: "速球", h: "inside", v: "mid", o: "solid", text: "左外野飛球出局", after: sit(4, "打者 D", 2) }),
  pitch({ seq: 48, ...OL, o: "take", text: "壞球", dy: -0.07, after: sit(4, "打者 D", 2, 1, 0) }),
  pitch({ seq: 49, ...OH, o: "weak", text: "二壘滾地出局", dv: -1, after: sit(6, "打者 A", 0) }),
  // ── 6 局上：展演起點 ──
  paStart("pa-6a", "6 局上・打者 A 上場", sit(6, "打者 A", 0), "打者上場：自動帶入投打者、壘上無人、0-0（距離尚遠）"),
  pitch({ seq: 61, ...OH, o: "take", text: "壞球", dx: 0.07, dy: 0.05, after: sit(6, "打者 A", 0, 1, 0),
    script: "符合條件的新一球：未出棒 → 接近區內" }),
  pitch({ seq: 62, ...OH, o: "foul", text: "界外", dv: 1, after: sit(6, "打者 A", 0, 1, 1),
    script: "符合條件的新一球：界外 → 已超過" }),
  pitch({ seq: 63, ...OH, o: "whiff", text: "揮空", dy: 0.08, dv: 1, after: sit(6, "打者 A", 0, 1, 2),
    script: "符合戰術目的的新證據：追打揮空 → 回落" }),
  pitch({ seq: 64, pitch: "速球", h: "inside", v: "high", o: "take", text: "壞球", dx: -0.06, after: sit(6, "打者 A", 0, 2, 2),
    script: "不符合條件的新一球：球種相同、區域不符" }),
  pitch({ seq: 65, ...OH, o: "take", text: "壞球", dx: 0.08, dy: 0.06, dv: 2, after: sit(6, "打者 A", 0, 3, 2),
    script: "2-2 變 3-2：這一球記在 2-2；參考線改用 3-2 的值" }),
  pitch({ seq: 66, ...OL, o: "weak", text: "三壘滾地出局", after: sit(6, "打者 C", 1),
    script: "不符合條件的一球結束打席；換下一位打者，打者 C 帶入自己的資料" }),
  pitch({ seq: 67, ...OH, o: "take", text: "壞球", dx: 0.06, after: sit(6, "打者 C", 1, 1, 0),
    script: "符合條件的新一球（打者 C 自己的觀察）：未出棒" }),
  pitch({ seq: 68, ...OL, o: "whiff", text: "揮空", after: sit(6, "打者 C", 1, 1, 1),
    script: "不符合條件的新一球：球種、區域都不符" }),
  pitch({ seq: 69, ...OH, o: "whiff", text: "揮空", dy: 0.07, dv: 1, after: sit(6, "打者 C", 1, 1, 2),
    script: "符合戰術目的的新證據（打者 C）：追打揮空 → 回落" }),
];

export const REPLAY_START = DEMO_EVENTS.findIndex((e) => e.id === "pa-6a");

// ── 情蒐參考值（示意指標上的參考線）：直接寫好的模擬值 ──
export const COUNT_ORDER: readonly CountKey[] =
  ["0-0", "1-0", "2-0", "3-0", "0-1", "1-1", "2-1", "3-1", "0-2", "1-2", "2-2", "3-2"];
/** base＝兩好球前；twoStrike＝0-2、1-2、2-2；full＝3-2（滿球數另給一個值，不沿用其他兩好球）。 */
function ref(base: number, twoStrike: number, full: number): Partial<Record<CountKey, number>> {
  const out: Partial<Record<CountKey, number>> = {};
  for (const ck of COUNT_ORDER) out[ck] = ck === "3-2" ? full : ck.endsWith("-2") ? twoStrike : base;
  return out;
}
export const DEMO_REFERENCE: ReferenceTable = {
  "outside-high-fastball": { "打者 A": ref(80, 78, 74), "打者 C": ref(88, 86, 82) },
  "outside-low-slider": { "打者 A": ref(70, 68, 64), "打者 C": ref(72, 70, 66) },
};

// ── 情蒐基準（示意）：以簡表產生，每個精確球數一格 ──
type Shares = { whiff: number; foul: number; weak: number; hard: number };
/** ns＝各球數的符合條件來球數；swingPct＝出棒比例（%）；shares＝各類占出棒的比例，其餘算一般擊球。 */
function tbl(ns: number[], swingPct: number[], shares: Shares): CountTable {
  const out: CountTable = {};
  COUNT_ORDER.forEach((ck, i) => {
    const n = ns[i];
    let rest = Math.round((n * swingPct[i]) / 100);
    const take = n - rest;
    const part = (share: number) => { const k = Math.min(rest, Math.round((n - take) * share)); rest -= k; return k; };
    const whiff = part(shares.whiff), foul = part(shares.foul), weak = part(shares.weak), hard = part(shares.hard);
    const entry: BaselineEntry = [n, take, whiff, foul, weak, rest, hard];
    out[ck] = entry;
  });
  return out;
}

export const DEMO_BASELINES: BaselineTable = {
  "outside-high-fastball": {
    league: tbl([1840, 980, 420, 160, 1210, 1105, 640, 300, 880, 1290, 760, 212], [23, 26, 29, 9, 33, 39, 42, 47, 50, 53, 53, 66], { whiff: 0.24, foul: 0.4, weak: 0.16, hard: 0.07 }),
    pitcher: tbl([96, 48, 22, 12, 60, 55, 30, 16, 44, 70, 41, 24], [23, 25, 28, 8, 35, 40, 43, 48, 52, 57, 59, 70], { whiff: 0.36, foul: 0.36, weak: 0.14, hard: 0.05 }),
    batters: {
      "打者 A": {
        long: tbl([62, 35, 16, 12, 41, 38, 22, 14, 30, 44, 27, 18], [22, 26, 30, 8, 36, 42, 45, 50, 52, 55, 56, 68], { whiff: 0.34, foul: 0.36, weak: 0.14, hard: 0.05 }),
        recent: tbl([24, 14, 10, 10, 16, 15, 11, 10, 12, 17, 12, 10], [25, 28, 30, 10, 38, 47, 45, 50, 50, 58, 50, 60], { whiff: 0.3, foul: 0.38, weak: 0.12, hard: 0.08 }),
      },
      "打者 C": {
        long: tbl([55, 30, 15, 12, 36, 33, 20, 13, 28, 39, 25, 16], [15, 18, 20, 5, 28, 30, 33, 36, 40, 44, 46, 55], { whiff: 0.2, foul: 0.44, weak: 0.12, hard: 0.1 }),
        recent: tbl([20, 12, 10, 10, 14, 13, 10, 10, 11, 15, 11, 10], [15, 17, 20, 10, 29, 31, 30, 40, 36, 47, 45, 50], { whiff: 0.2, foul: 0.42, weak: 0.12, hard: 0.12 }),
      },
    },
  },
  "outside-low-slider": {
    league: tbl([1320, 760, 300, 120, 905, 840, 480, 220, 700, 990, 610, 150], [20, 23, 25, 7, 34, 38, 40, 44, 50, 53, 54, 62], { whiff: 0.4, foul: 0.24, weak: 0.22, hard: 0.05 }),
    pitcher: tbl([70, 40, 18, 10, 52, 46, 26, 14, 40, 60, 36, 20], [21, 24, 26, 8, 36, 40, 42, 46, 52, 56, 56, 66], { whiff: 0.44, foul: 0.22, weak: 0.22, hard: 0.04 }),
    batters: {
      "打者 A": {
        long: tbl([48, 30, 14, 10, 37, 33, 20, 12, 28, 40, 22, 14], [18, 20, 22, 6, 34, 38, 40, 42, 50, 52, 50, 58], { whiff: 0.42, foul: 0.22, weak: 0.24, hard: 0.04 }),
        recent: tbl([18, 12, 10, 10, 14, 13, 10, 10, 11, 15, 11, 10], [20, 22, 22, 8, 30, 36, 40, 40, 46, 54, 46, 55], { whiff: 0.4, foul: 0.24, weak: 0.22, hard: 0.05 }),
      },
      "打者 C": {
        long: tbl([50, 28, 14, 10, 34, 30, 18, 12, 26, 36, 22, 14], [24, 26, 28, 8, 40, 44, 46, 48, 56, 60, 58, 64], { whiff: 0.45, foul: 0.2, weak: 0.24, hard: 0.04 }),
        recent: tbl([19, 12, 10, 10, 13, 12, 10, 10, 11, 14, 10, 10], [26, 25, 30, 10, 38, 42, 50, 50, 55, 57, 60, 60], { whiff: 0.45, foul: 0.22, weak: 0.22, hard: 0.04 }),
      },
    },
  },
};

/** 各打者對投手 B 的過往對戰（示意，不含本場）。 */
export const DEMO_MATCHUP: Record<string, {
  period: string; pa: number; hits: number; so: number; bb: number;
  /** 各戰術條件下的來球數與反應次數（依序：未出棒、揮空、界外、無效擊球、一般擊球、強勁擊球） */
  byTactic: Record<string, BaselineEntry>;
}> = {
  "打者 A": {
    period: "2025–2026 例行賽", pa: 9, hits: 2, so: 3, bb: 1,
    byTactic: {
      "outside-high-fastball": [14, 9, 2, 2, 1, 0, 0],
      "outside-low-slider": [11, 7, 2, 1, 1, 0, 0],
    },
  },
  "打者 C": {
    period: "2025–2026 例行賽", pa: 7, hits: 1, so: 1, bb: 2,
    byTactic: {
      "outside-high-fastball": [10, 8, 0, 1, 0, 0, 1],
      "outside-low-slider": [9, 4, 2, 1, 2, 0, 0],
    },
  },
};

/** 投手 B 各球種的賽前參考均速（示意，km/h），供量測對照。 */
export const DEMO_PITCHER_REF_SPEED: Record<string, number> = { 速球: 146.5, 滑球: 131.4, 變速: 127.8 };

// ── 各打者長期來球點（示意）：以固定種子產生，供既有進壘點／熱區圖元件使用 ──
export type DemoPoint = {
  pitch: string; x: number; y: number; sw: boolean; wh: boolean;
  result: ZoneResult; ev: number | null; la: number | null;
};
function lcg(seed: number) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
function gauss(r: () => number) {
  const u = Math.max(r(), 1e-9), v = r();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
function buildPoints(seed: number, chase: number): DemoPoint[] {
  const r = lcg(seed);
  // 座標取到千分位：Math.log／cos 在 Node 與瀏覽器的末位可能不同，避免 SSR 水合不一致
  const r3 = (v: number) => Math.round(v * 1000) / 1000;
  const out: DemoPoint[] = [];
  for (let i = 0; i < 360; i++) {
    const q0 = r();
    const pitch = q0 < 0.52 ? "速球" : q0 < 0.84 ? "滑球" : "變速";
    const breaking = pitch !== "速球";
    const x = Math.max(-0.49, Math.min(0.49, gauss(r) * 0.2 + (pitch === "滑球" ? 0.06 : 0)));
    const y = Math.max(0.16, Math.min(1.34, 0.75 + gauss(r) * (breaking ? 0.26 : 0.22) - (breaking ? 0.1 : -0.03)));
    const inZone = Math.abs(x) <= 0.21 && y >= 0.5 && y <= 1.0;
    const sw = r() < (inZone ? 0.66 : chase);
    const wh = sw && r() < (breaking ? 0.32 : 0.2);
    let result: ZoneResult = "take";
    let ev: number | null = null, la: number | null = null;
    if (sw && wh) result = "whiff";
    else if (sw) {
      const q = r();
      if (q < 0.42) result = "foul";
      else {
        result = q < 0.62 ? "hit" : "out";
        ev = Math.round(120 + r() * 45);
        la = Math.round((y - 0.75) * 40 + gauss(r) * 14);
      }
    }
    out.push({ pitch, x: r3(x), y: r3(y), sw, wh, result, ev, la });
  }
  return out;
}
export const DEMO_LONG_POINTS: Record<string, DemoPoint[]> = {
  "打者 A": buildPoints(452, 0.34),
  "打者 C": buildPoints(453, 0.24),
};
