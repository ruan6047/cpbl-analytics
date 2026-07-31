import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  applyLiveSnapshot,
  canShowPostgameConclusions,
  isTopHalf,
  lineupMessage,
  nextPollDelay,
  resolveStatusSnapshot,
  shouldFetchLivePayload,
  trackingPendingMessage,
  type LiveApiResponse,
  type LiveSnapshot,
} from "./live-game.ts";

const snapshot = (overrides: Partial<LiveSnapshot> = {}): LiveSnapshot => ({
  game_id: "2026-A-231",
  game_sno: 231,
  kind_code: "A",
  phase: "live",
  raw_status: "START",
  inning: 1,
  half: "top",
  event_count: 2,
  tracking_count: 0,
  tracking_availability: "pending",
  poll_after_seconds: 12,
  freshness: "fresh",
  source_status: "ok",
  stale_after_seconds: 45,
  source: { fetched_at: "2026-07-30T13:00:00+00:00", version: "v1" },
  away: {
    team: { code: "AAA", name: "客隊" }, score: 1,
    inning_score: [{ Seq: 1, Score: "1" }],
    lineup: { availability: "announced", items: [], first_observed_at: null },
    hitters: [{ HitterAcnt: "11", HitterName: "客隊一棒", Avg: 0.3 }], pitchers: [],
    probable_pitcher: { availability: "not_announced" },
  },
  home: {
    team: { code: "BBB", name: "主隊" }, score: 0,
    inning_score: [{ Seq: 1, Score: "0" }],
    lineup: { availability: "partial", items: [], first_observed_at: null },
    hitters: [], pitchers: [], probable_pitcher: { availability: "not_announced" },
  },
  livelog: [
    { MainEventNo: "1", VisitingHomeType: "1", InningSeq: 1, VisitingScore: 0, HomeScore: 0,
      IsChangePlayer: "0", Content: "壞球。", HitterAcnt: "11", HitterName: "客隊一棒" },
    { MainEventNo: "2", VisitingHomeType: "1", InningSeq: 1, VisitingScore: 1, HomeScore: 0,
      IsChangePlayer: "0", Content: "適時安打。", HitterAcnt: "11", HitterName: "客隊一棒" },
  ],
  ...overrides,
});

const response = (liveSnapshot: LiveSnapshot | null): LiveApiResponse => ({
  game: { away_score: 0, home_score: 0, away_team_name: "舊客隊", home_team_name: "舊主隊" },
  scoreboard: [], livelog: [], batting: [], pitching: [], people: {}, records: {}, batter_avg: {},
  detail: null, decisions: {}, decision_counts: null, has_tracking: false, tracking: [], spray: [],
  live_snapshot: liveSnapshot,
});

test("live 前景依 API 建議 12 秒輪詢，背景與 final 都停止 timer", () => {
  assert.equal(nextPollDelay(snapshot(), true), 12_000);
  assert.equal(nextPollDelay(snapshot(), false), null);
  assert.equal(nextPollDelay(snapshot({ phase: "final", poll_after_seconds: null }), true), null);
  assert.equal(nextPollDelay(snapshot({ phase: "scheduled", poll_after_seconds: null }), true), 60_000);
});

test("canonical half 同時接受 worker 的 1/2 與語意化 top/bottom", () => {
  assert.equal(isTopHalf("1"), true);
  assert.equal(isTopHalf(1), true);
  assert.equal(isTopHalf("top"), true);
  assert.equal(isTopHalf("2"), false);
  assert.equal(isTopHalf("bottom"), false);
});

test("status 只有事件數增加或尚無本地快照時才抓 full live payload", () => {
  assert.equal(shouldFetchLivePayload(null, snapshot()), true);
  assert.equal(shouldFetchLivePayload(snapshot(), snapshot()), false);
  assert.equal(shouldFetchLivePayload(snapshot(), snapshot({ event_count: 3 })), true);
  assert.equal(shouldFetchLivePayload(snapshot(), snapshot({ source_status: "error" })), false);
});

test("live 即使已有比分也不得啟用賽後結論，只有 final 或歷史無 snapshot 場可啟用", () => {
  assert.equal(canShowPostgameConclusions(snapshot({ phase: "live" }), 2), false);
  assert.equal(canShowPostgameConclusions(snapshot({ phase: "reserved" }), 2), false);
  assert.equal(canShowPostgameConclusions(snapshot({ phase: "final" }), 2), true);
  assert.equal(canShowPostgameConclusions(null, 2), true);
  assert.equal(canShowPostgameConclusions(null, 0), false);
});

test("status 200 但 snapshot null 時保留 last-known-good 並標示來源中斷", () => {
  const previous = snapshot();
  assert.deepEqual(resolveStatusSnapshot(previous, null), {
    accepted: false,
    interrupted: true,
    snapshot: previous,
  });
  const next = snapshot({ event_count: 3 });
  assert.deepEqual(resolveStatusSnapshot(previous, next), {
    accepted: true,
    interrupted: false,
    snapshot: next,
  });
});

test("canonical snapshot 覆蓋每日 DB 的比分與事件，並正規化 raw 欄位", () => {
  const live = snapshot();
  live.away.inning_score = [{ Seq: 1, Score: "1" }, { Seq: 2, Score: "0" }];
  live.away.hitters = [{ HitterAcnt: "11", HitterName: "客隊一棒", HitCnt: 3, HittingCnt: 2, Avg: 0.3 }];
  const out = applyLiveSnapshot(response(live));
  assert.equal(out.game?.away_score, 1);
  assert.equal(out.game?.home_score, 0);
  assert.equal(out.game?.away_team_name, "客隊");
  assert.equal(out.livelog.length, 2);
  assert.equal(out.livelog[0].main_event_no, "1");
  assert.equal(out.livelog[0].is_change_player, false);
  assert.equal(out.livelog[1].is_score, true);
  assert.equal(out.scoreboard[0].visiting_home_type, "1");
  assert.equal(out.game?.away_hits, 2);
  assert.equal(out.scoreboard.every((row) => row.hitting_cnt === null && row.error_cnt === null), true);
  assert.equal(out.batting[0].hitter_acnt, "11");
  assert.equal(out.batter_avg["11"], 0.3);
  assert.equal(out.live_snapshot?.phase, "live");
});

test("賽中 TrackMan 缺資料的所有入口都使用中性整理中文案", () => {
  assert.match(trackingPendingMessage(snapshot()), /賽中逐球追蹤尚在整理/);
  assert.doesNotMatch(trackingPendingMessage(snapshot()), /未設置|無設備/);
  const boxTabs = readFileSync(new URL("../app/games/[sno]/box-tabs.tsx", import.meta.url), "utf8");
  assert.match(boxTabs, /trackingPendingMessage\(data\.live_snapshot\)/);
});

test("前端 union 對齊 backend 可輸出的賽前與 tracking availability", () => {
  assert.equal(nextPollDelay(snapshot({ phase: "probable_announced" }), true), 60_000);
  const pending = snapshot({ tracking_availability: "not_announced" });
  assert.equal(pending.tracking_availability, "not_announced");
});

test("stale 或 source error 仍保留 last-known-good 事件", () => {
  const stale = snapshot({ freshness: "stale", source_status: "error" });
  const out = applyLiveSnapshot(response(stale));
  assert.equal(out.livelog.length, 2);
  assert.equal(out.live_snapshot?.freshness, "stale");
  assert.equal(out.live_snapshot?.source_status, "error");
});

test("兩隊 lineup 可各自 partial，stale/error 不偽裝成未公布", () => {
  assert.equal(lineupMessage("announced", "fresh", "ok"), "已公布");
  assert.equal(lineupMessage("partial", "fresh", "ok"), "部分公布");
  assert.equal(lineupMessage("not_announced", "fresh", "ok"), "尚未公布");
  assert.equal(lineupMessage("announced", "stale", "ok"), "資料可能已過期（保留最近名單）");
  assert.equal(lineupMessage("announced", "fresh", "error"), "來源中斷（保留最近名單）");
});
