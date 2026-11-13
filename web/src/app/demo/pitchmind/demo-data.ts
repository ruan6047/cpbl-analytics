// PitchMind 示意頁：**事先設計好的模擬序列**（#452）。
//
// 全部為手編示意：球員匿名（打者 A、投手 B…），不對應任何真實球員或比賽，也不取自
// ~/Dev/Rebas 研究檔或本站正式資料。正式資料要另建資料檔並在 view 層換 import；
// ⛔ 不要把正式資料寫進本檔。
//
// 劇本（外角高速球，參考值 兩好球前 80／兩好球 75）：
//   載入時 30（距離尚遠）→ 42 → 50 → 62（3-2，正在接近）→ 70 → 82（已超過）
//   → 第 10 事件安排的明顯不利結果（全壘打）94 → 追打揮空回落 82 → 70 → 弱擊球出局 60（距離尚遠）。
//   提示（接近、超過）刻意排在明顯不利結果之前：這是設計好的示意，不是提前預警成效證明。

import type { GameEvent, HLoc, PitchEvent, Reaction, Situation, VLoc, ZoneResult } from "./model.ts";

const EMPTY = { first: false, second: false, third: false };
const sit = (inning: number, batter: string, outs: number, balls = 0, strikes = 0): Situation => ({
  inning, half: "top", batter, batterHand: "R", pitcher: "投手 B", balls, strikes, outs, bases: EMPTY,
});

// 位置 → 示意座標（捕手視角；右打者外角在 +x）。
const X: Record<HLoc, number> = { inside: -0.27, middle: 0.0, outside: 0.27 };
const Y: Record<VLoc, number> = { high: 1.08, mid: 0.76, low: 0.42 };
const SPEED: Record<string, number> = { 速球: 147, 滑球: 132, 變速: 128 };

type P = {
  seq: number; pitch: string; h: HLoc; v: VLoc; reaction: Reaction; zone: ZoneResult;
  text: string; after: Situation; script?: string; dx?: number; dy?: number; dv?: number;
};
const pitch = (p: P): PitchEvent => ({
  kind: "pitch", id: `ev-${p.seq}`, seq: p.seq, label: `全場第 ${p.seq} 球`,
  pitch: p.pitch, h: p.h, v: p.v, x: X[p.h] + (p.dx ?? 0), y: Y[p.v] + (p.dy ?? 0),
  speed: (SPEED[p.pitch] ?? 140) + (p.dv ?? 0), reaction: p.reaction, zoneResult: p.zone,
  resultText: p.text, after: p.after, script: p.script,
});
const paStart = (id: string, label: string, after: Situation, script?: string): GameEvent =>
  ({ kind: "pa_start", id, label, after, script });

const OH = { pitch: "速球", h: "outside", v: "high" } as const;
const OL = { pitch: "滑球", h: "outside", v: "low" } as const;
const IH = { pitch: "速球", h: "inside", v: "high" } as const;

export const DEMO_EVENTS: GameEvent[] = [
  // ── 載入前已發生（1、4 局）──
  paStart("pa-1", "1 局上・打者 A 上場", sit(1, "打者 A", 0)),
  pitch({ seq: 1, ...OH, reaction: "take", zone: "take", text: "壞球", dx: 0.06, after: sit(1, "打者 A", 0, 1, 0) }),
  pitch({ seq: 2, ...OH, reaction: "foul", zone: "foul", text: "界外", after: sit(1, "打者 A", 0, 1, 1) }),
  pitch({ seq: 3, ...OL, reaction: "weak", zone: "out", text: "二壘滾地出局", after: sit(1, "打者 C", 1) }),
  pitch({ seq: 4, ...OH, reaction: "take", zone: "take", text: "壞球", dy: 0.06, after: sit(1, "打者 C", 1, 1, 0) }),
  pitch({ seq: 5, ...IH, reaction: "hard", zone: "out", text: "強勁平飛球被接殺", after: sit(1, "打者 D", 2) }),
  pitch({ seq: 6, ...OL, reaction: "take", zone: "take", text: "壞球", dy: -0.05, after: sit(1, "打者 D", 2, 1, 0) }),
  pitch({ seq: 7, ...OH, reaction: "weak", zone: "out", text: "內野高飛球出局", after: sit(4, "打者 A", 0) }),
  pitch({ seq: 41, ...IH, reaction: "take", zone: "take", text: "壞球", dx: -0.05, after: sit(4, "打者 A", 0, 1, 0) }),
  pitch({ seq: 42, ...OH, reaction: "foul", zone: "foul", text: "界外", after: sit(4, "打者 A", 0, 1, 1) }),
  pitch({ seq: 43, ...OL, reaction: "foul", zone: "foul", text: "界外", after: sit(4, "打者 A", 0, 1, 2) }),
  pitch({ seq: 44, ...IH, reaction: "hard", zone: "out", text: "強勁平飛球被接殺", after: sit(4, "打者 C", 1) }),
  pitch({ seq: 45, ...IH, reaction: "foul", zone: "foul", text: "界外", after: sit(4, "打者 C", 1, 0, 1) }),
  pitch({ seq: 46, ...OH, reaction: "called", zone: "take", text: "好球（未揮）", dx: -0.04, after: sit(4, "打者 C", 1, 0, 2) }),
  pitch({ seq: 47, pitch: "變速", h: "middle", v: "low", reaction: "whiff", zone: "whiff", text: "揮空三振", after: sit(4, "打者 D", 2) }),
  pitch({ seq: 48, ...IH, reaction: "weak", zone: "out", text: "游擊滾地出局", after: sit(6, "打者 A", 0) }),
  // ── 6 局上：展演起點 ──
  paStart("pa-6a", "6 局上・打者 A 上場", sit(6, "打者 A", 0), "自動帶入打者 A、壘上無人、0-0；外角高速球距參考界線尚遠"),
  pitch({ seq: 61, ...OH, reaction: "take", zone: "take", text: "壞球", dx: 0.07, dy: 0.05, after: sit(6, "打者 A", 0, 1, 0) }),
  pitch({ seq: 62, ...OL, reaction: "whiff", zone: "whiff", text: "揮空", after: sit(6, "打者 A", 0, 1, 1) }),
  pitch({ seq: 63, ...OH, reaction: "foul", zone: "foul", text: "界外", dv: 1, after: sit(6, "打者 A", 0, 1, 2),
    script: "進入兩好球：外角高速球的參考界線依示意規則由 80 改為 75，累積延續" }),
  pitch({ seq: 64, ...OL, reaction: "take", zone: "take", text: "壞球", dy: -0.06, after: sit(6, "打者 A", 0, 2, 2) }),
  pitch({ seq: 65, ...OH, reaction: "take", zone: "take", text: "壞球", dx: 0.08, dy: 0.06, dv: 2, after: sit(6, "打者 A", 0, 3, 2),
    script: "2-2 → 3-2：仍是兩好球，界線維持 75；動態值進入接近區" }),
  pitch({ seq: 66, ...OH, reaction: "foul", zone: "foul", text: "界外", dv: 1, after: sit(6, "打者 A", 0, 3, 2) }),
  pitch({ seq: 67, ...IH, reaction: "weak", zone: "out", text: "右外野飛球出局", after: sit(6, "打者 C", 1),
    script: "換打者回到 0-0：界線回到 80，外角高速球的累積延續" }),
  pitch({ seq: 68, ...OH, reaction: "hard", zone: "foul", text: "強勁擊球界外", dv: 1, after: sit(6, "打者 C", 1, 0, 1),
    script: "動態值超過參考界線（提示出現；此時尚未發生明顯不利結果）" }),
  pitch({ seq: 69, ...OL, reaction: "weak", zone: "out", text: "游擊滾地出局", after: sit(6, "打者 D", 2) }),
  pitch({ seq: 70, ...OH, reaction: "hard", zone: "hit", text: "左外野全壘打", dv: 1, after: sit(6, "打者 E", 2),
    script: "事先安排的明顯不利結果（全壘打），排在提示之後；這是設計好的示意，不是提前預警成效證明" }),
  pitch({ seq: 71, ...OH, reaction: "whiff", zone: "whiff", text: "追打揮空", dy: 0.07, after: sit(6, "打者 E", 2, 0, 1),
    script: "符合預期的觀察：動態值開始回落" }),
  pitch({ seq: 72, ...OH, reaction: "whiff", zone: "whiff", text: "追打揮空", dy: 0.08, dv: 1, after: sit(6, "打者 E", 2, 0, 2) }),
  pitch({ seq: 73, ...OH, reaction: "weak", zone: "out", text: "捕手界外飛球出局", after: sit(7, "打者 F", 0),
    script: "回落到距離尚遠" }),
];

export const REPLAY_START = DEMO_EVENTS.findIndex((e) => e.id === "pa-6a");
/** 事先安排的明顯不利結果（全壘打）事件 id，測試用來確認提示排在它之前。 */
export const SCRIPTED_ADVERSE_EVENT_ID = "ev-70";
