import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { pageCompletedOf } from "./highlights-parity.ts";
import {
  applyLiveSnapshot, applyLiveSnapshotUnreconciled, FINAL_PENDING_LABEL, gamePageStatus, LIVE_REFETCH_MS,
  liveRefetchDue, nextPollDelay, reconcileLiveSnapshot, resolveStatusSnapshot, type GamePageStatus,
  type LiveApiResponse,
} from "./live-game.ts";
import { cardStatus, chipView } from "./playoffs-series-view.ts";
import type { OverviewGameCard } from "./playoffs-types.ts";

// #345 W3：終場後單場頁的兩類錯誤事實（plan-1 §4）。夾具＝正式站真實回應裁短陣列，來源與 sha256 見 _provenance。
//   * G4 形狀：DB 已完賽 4:5、快照停在 live 4:4 下11局（stale）→ 修正前單場頁「比賽進行中 4:4」。
//   * G3 形狀：快照 final 但比分 0:0、DB 未完賽 → 修正前單場頁「比賽結束 0:0」（變異樣本，見各測試）。
// 每個正控都另跑修正前路徑（`applyLiveSnapshotUnreconciled`＋不對帳），證明檢查抓得到原缺陷。

const FX = JSON.parse(readFileSync(new URL("./__fixtures__/live-reconcile_2026-C3-C4.json", import.meta.url), "utf8")) as {
  g4_r140: LiveApiResponse;
  g4_r143: LiveApiResponse;
  c3_probe: LiveApiResponse;
  c4_probe: LiveApiResponse;
  g4_r143_playoffs_card: OverviewGameCard;
};
const sample = (key: "g4_r140" | "g4_r143" | "c3_probe" | "c4_probe") => structuredClone(FX[key]);

/** G3 21:24:32 的 /live：c3_probe 的不可變 final 快照（21:23:46）＋當時觀測的 DB 狀態（0:0、四表 0 列）。 */
const g3At212432 = (): LiveApiResponse => {
  const raw = sample("c3_probe");
  return {
    ...raw,
    game: { ...raw.game, away_score: 0, home_score: 0, completed: false },
    scoreboard: [], livelog: [], batting: [], pitching: [],
  };
};

const legacy = (raw: LiveApiResponse): GamePageStatus =>
  gamePageStatus(raw, applyLiveSnapshotUnreconciled, () => "as_is");

/** 錯誤事實判定（需求判準）：DB 已完賽卻顯示進行中／非終場比分；或 DB 未完賽卻把 0:0 當終場。 */
const wrongFact = (raw: LiveApiResponse, s: GamePageStatus): string | null => {
  const db = raw.game ?? {};
  if (db.completed === true) {
    if (s.kind !== "final") return `DB 完賽卻顯示 ${s.label}`;
    if (s.away !== Number(db.away_score) || s.home !== Number(db.home_score)) return `比分 ${s.away}:${s.home} ≠ DB`;
    return null;
  }
  if (s.kind === "final" && s.away + s.home === 0) return "未完賽 0:0 被當終場";
  return null;
};

test("夾具身分：四份真實樣本的場次、DB 狀態與快照 phase 如 _provenance 所述", () => {
  const r140 = sample("g4_r140"), r143 = sample("g4_r143"), c3 = sample("c3_probe"), c4 = sample("c4_probe");
  assert.deepEqual([r140.game?.completed, r140.live_snapshot?.phase, r140.live_snapshot?.freshness], [false, "live", "stale"]);
  assert.deepEqual([r143.game?.completed, r143.game?.away_score, r143.game?.home_score], [true, 4, 5]);
  assert.deepEqual([r143.live_snapshot?.phase, r143.live_snapshot?.away.score, r143.live_snapshot?.home.score], ["live", 4, 4]);
  assert.deepEqual([c3.live_snapshot?.phase, c3.live_snapshot?.away.score, c3.live_snapshot?.home.score], ["final", 6, 0]);
  assert.equal(c3.live_snapshot?.source.fetched_at, "2026-10-20T13:23:46.690477+00:00");
  assert.deepEqual([c4.game?.completed, c4.live_snapshot?.phase, c4.live_snapshot?.away.score, c4.live_snapshot?.home.score],
    [true, "final", 4, 5]);
});

test("G4 正控（r143）：修正前單場頁＝「比賽進行中 4:4」＋更新中斷（錯誤事實）；修正後＝終場 4:5", () => {
  const raw = sample("g4_r143");
  const before = legacy(raw);
  assert.deepEqual(before, { kind: "live", label: "比賽進行中", away: 4, home: 4, interrupted: true });
  assert.equal(wrongFact(raw, before), "DB 完賽卻顯示 比賽進行中");

  assert.equal(reconcileLiveSnapshot(raw.game, raw.live_snapshot), "db_final");
  const after = gamePageStatus(raw);
  assert.deepEqual(after, { kind: "final", label: "終場", away: 4, home: 5, interrupted: false });
  assert.equal(wrongFact(raw, after), null);
  assert.equal(applyLiveSnapshot(raw).live_snapshot, null);
  // #337 焦點檢查走同一個疊加：頁面完賽＝true（修正前為 false）。
  assert.equal(pageCompletedOf(raw), true);
});

test("G4 跨頁（r143 同一輪）：/playoffs 場次卡＝終場 4:5，與修正後單場頁一致；/playoffs 本卡不改", () => {
  const card = structuredClone(FX.g4_r143_playoffs_card);
  assert.deepEqual(cardStatus(card), { text: "終場", tone: "done" });
  assert.deepEqual(chipView(card).rows.map((r) => r.value), ["4", "5"]);
  const page = gamePageStatus(sample("g4_r143"));
  assert.ok(page.kind === "final");
  assert.deepEqual([String(page.away), String(page.home)], ["4", "5"]);
});

test("G4 負控（r140）：DB 尚未完賽、快照 live stale——修正前後都是「比賽進行中 4:4」（系統尚不知終場，不算錯）", () => {
  const raw = sample("g4_r140");
  assert.equal(reconcileLiveSnapshot(raw.game, raw.live_snapshot), "as_is");
  const expected = { kind: "live", label: "比賽進行中", away: 4, home: 4, interrupted: true };
  assert.deepEqual(legacy(raw), expected);
  assert.deepEqual(gamePageStatus(raw), expected);
  assert.equal(wrongFact(raw, gamePageStatus(raw)), null);
});

test("G3 負控（21:24:32 真實組合）：快照 final 6:0、DB 0:0 未完賽——修正前後都是「比賽結束 6:0」，不誤報", () => {
  const raw = g3At212432();
  assert.equal(reconcileLiveSnapshot(raw.game, raw.live_snapshot), "as_is");
  const expected = { kind: "final", label: "比賽結束", away: 6, home: 0, interrupted: false };
  assert.deepEqual(legacy(raw), expected);
  assert.deepEqual(gamePageStatus(raw), expected);
  assert.equal(wrongFact(raw, gamePageStatus(raw)), null);
});

test("G3 正控（變異：同一份快照比分改 0:0，非觀測）：修正前「比賽結束 0:0」＝錯誤事實；修正後「已結束、資料更新中」", () => {
  const raw = g3At212432();
  const snap = raw.live_snapshot!;
  raw.live_snapshot = { ...snap, away: { ...snap.away, score: 0 }, home: { ...snap.home, score: 0 } };
  const before = legacy(raw);
  assert.deepEqual(before, { kind: "final", label: "比賽結束", away: 0, home: 0, interrupted: false });
  assert.equal(wrongFact(raw, before), "未完賽 0:0 被當終場");

  assert.equal(reconcileLiveSnapshot(raw.game, raw.live_snapshot), "final_pending");
  const after = gamePageStatus(raw);
  assert.deepEqual(after, { kind: "final_pending", label: FINAL_PENDING_LABEL });
  assert.equal(wrongFact(raw, after), null);
  assert.equal(pageCompletedOf(raw), false);
});

test("終態負控（C4 probe）：快照 final＋DB 完賽 4:5——修正前後都是「比賽結束 4:5」", () => {
  const raw = sample("c4_probe");
  assert.equal(reconcileLiveSnapshot(raw.game, raw.live_snapshot), "as_is");
  const expected = { kind: "final", label: "比賽結束", away: 4, home: 5, interrupted: false };
  assert.deepEqual(legacy(raw), expected);
  assert.deepEqual(gamePageStatus(raw), expected);
});

test("有證據 0:0 真和局（DB 完賽、快照 final 0:0）不被當成待確認：照 is_completed_game 呈現終場 0:0", () => {
  const raw = sample("c4_probe");
  const snap = raw.live_snapshot!;
  raw.game = { ...raw.game, away_score: 0, home_score: 0, completed: true };
  raw.live_snapshot = { ...snap, away: { ...snap.away, score: 0 }, home: { ...snap.home, score: 0 } };
  assert.equal(reconcileLiveSnapshot(raw.game, raw.live_snapshot), "as_is");
});

test("管轄邊界：A／D 或 2025 以前即使形狀相同也一律 as_is（行為不變）", () => {
  for (const [kind, id] of [["A", "2026-A-4"], ["D", "2026-D-4"], ["C", "2025-C-4"]] as const) {
    const raw = sample("g4_r143");
    raw.live_snapshot = { ...raw.live_snapshot!, kind_code: kind, game_id: id };
    assert.equal(reconcileLiveSnapshot(raw.game, raw.live_snapshot), "as_is", id);
    assert.notEqual(applyLiveSnapshot(raw).live_snapshot, null, id);
  }
});

test("輪詢：DB 已完賽後 /status 送來同樣停更的 live 快照，不接回、不算中斷", () => {
  const raw = sample("g4_r143");
  const resolved = resolveStatusSnapshot(null, raw.live_snapshot, { completed: true });
  assert.deepEqual(resolved, { accepted: false, interrupted: false, snapshot: null });
  // DB 未完賽時照舊接受並標中斷（r140）。
  const r140 = sample("g4_r140");
  const live = resolveStatusSnapshot(null, r140.live_snapshot, { completed: false });
  assert.equal(live.accepted, true);
  assert.equal(live.interrupted, true);
  // 之後真的 final 快照仍接受。
  const final = resolveStatusSnapshot(null, sample("c4_probe").live_snapshot, { completed: true });
  assert.equal(final.accepted, true);
});

test("輪詢：快照停更或終場待確認時至多每 60 秒重抓 /live；新鮮 live 與正常 final 不重抓", () => {
  const stale = sample("g4_r140").live_snapshot;
  const final = sample("c4_probe").live_snapshot;
  const t0 = 1_000_000;
  assert.equal(LIVE_REFETCH_MS, 60_000);
  assert.equal(liveRefetchDue(stale, false, t0, t0 + 59_999), false);
  assert.equal(liveRefetchDue(stale, false, t0, t0 + 60_000), true);
  assert.equal(liveRefetchDue({ ...stale!, freshness: "fresh", source_status: "error" }, false, t0, t0 + 60_000), true);
  assert.equal(liveRefetchDue({ ...stale!, freshness: "fresh" }, false, t0, t0 + 600_000), false);
  assert.equal(liveRefetchDue(final, false, t0, t0 + 600_000), false);
  assert.equal(liveRefetchDue(final, true, t0, t0 + 60_000), true);
  assert.equal(liveRefetchDue(null, false, t0, t0 + 600_000), false);
  // final 照舊停止輪詢；終場待確認改每 60 秒；背景分頁不輪詢。
  assert.equal(nextPollDelay(final, true), null);
  assert.equal(nextPollDelay(final, true, true), 60_000);
  assert.equal(nextPollDelay(final, false, true), null);
});
