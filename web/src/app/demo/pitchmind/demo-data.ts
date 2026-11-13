// PitchMind 示意頁：**示意資料**（#452）。
//
// 全部數字為手編示意值，球員全部匿名（打者 A／投手 B…），不對應任何真實球員或比賽，
// 也不取自 ~/Dev/Rebas 研究檔或本站任何正式資料來源。要換成正式資料時，另建資料檔並在
// view 層換掉 import；⛔ 不要把正式資料寫進本檔，兩者分檔管理。

import type {
  BaselineTable, Family, GameEvent, HLoc, PitchEvent, Situation, VLoc, ZoneResult,
} from "./model.ts";

/** 示意頁暫用的樣本門檻：n 未達此值顯示「樣本不足」。實際門檻待研究。 */
export const DEMO_MIN_N = 10;

const EMPTY = { first: false, second: false, third: false };
const sit = (inning: number, batter: string, outs: number, balls = 0, strikes = 0): Situation => ({
  inning, half: "top", batter, batterHand: "R", pitcher: "投手 B", balls, strikes, outs, bases: EMPTY,
});

// 位置 → 示意座標（捕手視角；右打者外角在 +x）。
const X: Record<HLoc, number> = { inside: -0.27, middle: 0.0, outside: 0.27 };
const Y: Record<VLoc, number> = { high: 1.08, mid: 0.76, low: 0.42 };

type P = {
  seq: number; family: Family; h: HLoc; v: VLoc; speed: number;
  r: ZoneResult; grounder?: boolean; text: string; after: Situation; dx?: number; dy?: number;
};
const pitch = (p: P): PitchEvent => {
  return {
    kind: "pitch", id: `ev-${p.seq}`, seq: p.seq,
    label: `全場第 ${p.seq} 球`,
    family: p.family, h: p.h, v: p.v,
    x: X[p.h] + (p.dx ?? 0), y: Y[p.v] + (p.dy ?? 0), speed: p.speed,
    swing: p.r !== "take", whiff: p.r === "whiff", grounder: !!p.grounder,
    zoneResult: p.r, resultText: p.text, after: p.after,
  };
};
const paStart = (id: string, label: string, after: Situation): GameEvent => ({ kind: "pa_start", id, label, after });

/**
 * 事件序列。展演從 REPLAY_START（6 局上打者 A 上場）開始；之前的事件是載入時已發生的本場資料，
 * 用來示範「已累積事件不因展演或切換而清除」。
 */
export const DEMO_EVENTS: GameEvent[] = [
  // ── 1 局上 ──
  paStart("pa-1", "1 局上・打者 A 上場", sit(1, "打者 A", 0)),
  pitch({ seq: 1, family: "fastball", h: "outside", v: "high", speed: 146, r: "foul", text: "界外", after: sit(1, "打者 A", 0, 0, 1) }),
  pitch({ seq: 2, family: "breaking", h: "inside", v: "low", speed: 129, r: "take", text: "壞球", after: sit(1, "打者 A", 0, 1, 1) }),
  pitch({ seq: 3, family: "fastball", h: "outside", v: "high", speed: 147, r: "whiff", text: "揮空", after: sit(1, "打者 A", 0, 1, 2) }),
  pitch({ seq: 4, family: "breaking", h: "outside", v: "low", speed: 128, r: "whiff", text: "揮空三振", after: sit(1, "打者 C", 1) }),
  pitch({ seq: 5, family: "fastball", h: "outside", v: "high", speed: 145, r: "take", text: "好球（未揮）", dx: 0.03, after: sit(1, "打者 C", 1, 0, 1) }),
  pitch({ seq: 6, family: "breaking", h: "inside", v: "low", speed: 130, r: "out", grounder: true, text: "游擊滾地出局", after: sit(1, "打者 E", 2) }),
  // ── 4 局上 ──
  paStart("pa-2", "4 局上・打者 A 上場", sit(4, "打者 A", 0)),
  pitch({ seq: 41, family: "breaking", h: "inside", v: "low", speed: 131, r: "foul", text: "界外", dy: 0.04, after: sit(4, "打者 A", 0, 0, 1) }),
  pitch({ seq: 42, family: "fastball", h: "outside", v: "high", speed: 147, r: "take", text: "壞球", dy: 0.06, after: sit(4, "打者 A", 0, 1, 1) }),
  pitch({ seq: 43, family: "fastball", h: "middle", v: "mid", speed: 146, r: "out", grounder: true, text: "一壘滾地出局", after: sit(4, "打者 D", 1) }),
  pitch({ seq: 44, family: "fastball", h: "outside", v: "high", speed: 148, r: "whiff", text: "揮空", after: sit(4, "打者 D", 1, 0, 1) }),
  pitch({ seq: 45, family: "fastball", h: "outside", v: "high", speed: 147, r: "out", text: "右外野飛球出局", dx: -0.04, after: sit(4, "打者 F", 2) }),
  // ── 6 局上（展演起點）──
  paStart("pa-3", "6 局上・打者 A 上場", sit(6, "打者 A", 0)),
  pitch({ seq: 61, family: "fastball", h: "outside", v: "high", speed: 147, r: "take", text: "壞球", dx: 0.05, dy: 0.05, after: sit(6, "打者 A", 0, 1, 0) }),
  pitch({ seq: 62, family: "breaking", h: "inside", v: "low", speed: 128, r: "whiff", text: "揮空", after: sit(6, "打者 A", 0, 1, 1) }),
  pitch({ seq: 63, family: "fastball", h: "outside", v: "high", speed: 148, r: "foul", text: "界外", dx: -0.03, after: sit(6, "打者 A", 0, 1, 2) }),
  pitch({ seq: 64, family: "breaking", h: "outside", v: "low", speed: 127, r: "take", text: "壞球", dy: -0.06, after: sit(6, "打者 A", 0, 2, 2) }),
  pitch({ seq: 65, family: "fastball", h: "outside", v: "high", speed: 149, r: "take", text: "壞球", dx: 0.07, dy: 0.06, after: sit(6, "打者 A", 0, 3, 2) }),
  pitch({ seq: 66, family: "breaking", h: "inside", v: "low", speed: 129, r: "out", grounder: true, text: "三壘滾地出局", after: sit(6, "打者 C", 1) }),
];

export const REPLAY_START = DEMO_EVENTS.findIndex((e) => e.id === "pa-3");

/** 「打者」基準只建了打者 A；其他打者顯示缺值。 */
export const DEMO_BATTER_WITH_BASELINE = "打者 A";

/**
 * 情蒐基準（示意）：[符合條件來球 n, 出棒, 揮空, 出棒中擊成滾地]。
 * 故意設計的狀態：3-2 打者長期／近期樣本不足；外角高近期 2-2 出棒觀察到 0 次；
 * 內角低的投手分項整列缺值。
 */
export const DEMO_BASELINES: BaselineTable = {
  "outside-high": {
    long: {
      "0-0": [62, 14, 3, 1], "0-1": [41, 15, 5, 1], "1-0": [35, 9, 2, 1], "1-1": [38, 16, 5, 2],
      "1-2": [44, 24, 10, 2], "2-2": [27, 15, 6, 1], "3-2": [7, 5, 1, 0],
    },
    recent: {
      "0-0": [12, 3, 1, 0], "0-1": [8, 3, 1, 0], "1-0": [6, 2, 0, 0], "1-1": [10, 4, 1, 0],
      "1-2": [11, 7, 3, 0], "2-2": [11, 0, 0, 0], "3-2": [3, 2, 0, 0],
    },
    league: {
      "0-0": [1840, 420, 61, 30], "0-1": [1210, 402, 88, 33], "1-0": [980, 251, 41, 22], "1-1": [1105, 430, 92, 35],
      "1-2": [1290, 690, 196, 48], "2-2": [760, 405, 104, 27], "3-2": [212, 168, 38, 12],
    },
    pitcher: {
      "0-0": [96, 22, 5, 2], "0-1": [60, 21, 7, 1], "1-0": [48, 12, 3, 1], "1-1": [55, 22, 8, 2],
      "1-2": [70, 40, 17, 3], "2-2": [41, 24, 9, 2], "3-2": [12, 9, 2, 1],
    },
  },
  "inside-low": {
    long: {
      "0-0": [48, 9, 2, 4], "0-1": [37, 13, 4, 6], "1-0": [30, 8, 2, 4], "1-1": [33, 12, 3, 5],
      "1-2": [40, 19, 6, 8], "2-2": [22, 11, 3, 5], "3-2": [5, 3, 0, 2],
    },
    recent: {
      "0-0": [9, 2, 0, 1], "0-1": [7, 2, 1, 1], "1-0": [5, 1, 0, 1], "1-1": [8, 3, 1, 1],
      "1-2": [10, 5, 2, 2], "2-2": [6, 3, 1, 1], "3-2": [2, 1, 0, 1],
    },
    league: {
      "0-0": [1320, 260, 48, 110], "0-1": [905, 330, 77, 128], "1-0": [760, 190, 35, 80], "1-1": [840, 320, 70, 124],
      "1-2": [990, 520, 150, 190], "2-2": [610, 330, 88, 120], "3-2": [150, 110, 22, 40],
    },
    pitcher: {
      "0-0": null, "0-1": null, "1-0": null, "1-1": null, "1-2": null, "2-2": null, "3-2": null,
    },
  },
};

/** 打者 A 對投手 B 的過往對戰（示意，不含本場）。 */
export const DEMO_MATCHUP = {
  period: "2025–2026 例行賽（示意）",
  pa: 9, hits: 2, so: 3, bb: 1,
  byTactic: {
    "outside-high": { pitches: 14, swing: 5, whiff: 2, grounder: 0 },
    "inside-low": { pitches: 11, swing: 4, whiff: 1, grounder: 2 },
  } as Record<string, { pitches: number; swing: number; whiff: number; grounder: number }>,
};

// ── 長期來球點（示意）：以固定種子產生，供既有進壘點／熱區圖元件使用 ──
export type DemoPoint = {
  family: Family; x: number; y: number; sw: boolean; wh: boolean;
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
function buildPoints(): DemoPoint[] {
  const r = lcg(452);
  const out: DemoPoint[] = [];
  for (let i = 0; i < 320; i++) {
    const family: Family = r() < 0.55 ? "fastball" : "breaking";
    const x = Math.max(-0.49, Math.min(0.49, gauss(r) * 0.2));
    const y = Math.max(0.16, Math.min(1.34, 0.75 + gauss(r) * (family === "breaking" ? 0.26 : 0.22) - (family === "breaking" ? 0.08 : 0)));
    const inZone = Math.abs(x) <= 0.21 && y >= 0.5 && y <= 1.0;
    const sw = r() < (inZone ? 0.66 : 0.3);
    const wh = sw && r() < (family === "breaking" ? 0.32 : 0.2);
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
    // 座標取到千分位：Math.log／cos 在 Node 與瀏覽器的末位可能不同，避免 SSR 水合不一致
    const r3 = (v: number) => Math.round(v * 1000) / 1000;
    out.push({ family, x: r3(x), y: r3(y), sw, wh, result, ev, la });
  }
  return out;
}
export const DEMO_LONG_POINTS: DemoPoint[] = buildPoints();
