import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  applyLiveSnapshot,
  canShowPostgameConclusions,
  hasStartedPlay,
  inningLabel,
  isTopHalf,
  lineupMessage,
  liveScorebarScores,
  nextPollDelay,
  plateAppearancePitchCountLabel,
  resolveStatusSnapshot,
  shouldFetchLivePayload,
  officialLivePitchCall,
  trackingEmptyMessage,
  trackingPendingMessage,
  trackmanAvailability,
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

test("頂部記分條以 snapshot 累計比分為準，不被最後事件的滯後比分倒退", () => {
  assert.deepEqual(
    liveScorebarScores(
      { away_score: 5, home_score: 0 },
      { visiting_score: 4, home_score: 0 },
    ),
    { away: 5, home: 0 },
  );
  assert.deepEqual(
    liveScorebarScores({}, { visiting_score: 4, home_score: 0 }), { away: 4, home: 0 });
  assert.deepEqual(
    liveScorebarScores({ away_score: null }, { visiting_score: 4 }), { away: 4, home: 0 });
});

test("賽況 Hero 收納狀態、賽事脈絡與更新時間，頁面不再另設狀態卡或返回連結", () => {
  const board = readFileSync(new URL("../components/game-board.tsx", import.meta.url), "utf8");
  const page = readFileSync(new URL("../app/games/[sno]/game-live-page.tsx", import.meta.url), "utf8");
  assert.match(board, /phaseLabel\(snapshot\.phase\)/);
  assert.match(board, /最後更新/);
  assert.match(board, /賽事編號/);
  assert.ok(board.indexOf("<ScoreBar") < board.indexOf("{tabs}"), "Hero 必須在主頁籤上方");
  assert.doesNotMatch(page, /← 返回賽況列表/);
  assert.doesNotMatch(page, /最後更新 \{liveSnapshot\.source\.fetched_at/);
});

test("收合打席標示整個打席實際用球數，不標示隱藏球數", () => {
  assert.equal(plateAppearancePitchCountLabel(3), "（3 球）");
  assert.equal(plateAppearancePitchCountLabel(1), "（1 球）");
});

test("收合打席把總球數放在投打名稱後，而非結果行後", () => {
  const board = readFileSync(new URL("../components/game-board.tsx", import.meta.url), "utf8");
  assert.match(board, /⚾ \{g\.name\}\s*\{g\.idxs\.length > 1 && <span[^>]*>\{plateAppearancePitchCountLabel\(g\.idxs\.length\)\}<\/span>\}/);
  assert.doesNotMatch(board, /lineBtn\(outcomeIdx, true,\s*g\.idxs\.length > 1 \? <span[^>]*>\{plateAppearancePitchCountLabel/);
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

// 生產實測（2026-07-31）：worker 對 SCHEDULED 場回 inning=1／half=1／event_count=0 佔位，
// 對 FINISHED 場回 inning=9／half=2 真值。只判 inning truthy 會讓未開賽顯示「▲ 1 局」。
test("未開打場次不顯示局數，即使 worker 回 inning=1 佔位", () => {
  const pre = { inning: 1, half: "1", event_count: 0 } as const;
  for (const phase of ["scheduled", "probable_announced", "lineup_announced"] as const) {
    const s = snapshot({ phase, raw_status: "SCHEDULED", ...pre });
    assert.equal(hasStartedPlay(s), false, `${phase} 不應視為已開打`);
    assert.equal(inningLabel(s, "glyph"), null, `${phase} 不應顯示局數`);
    assert.equal(inningLabel(s, "text"), null, `${phase} 不應播報局數`);
  }
});

test("已開打場次照常顯示局數；上下半局對應 worker 的 1/2", () => {
  const live = snapshot({ phase: "live", inning: 4, half: "1", event_count: 12 });
  assert.equal(hasStartedPlay(live), true);
  assert.equal(inningLabel(live, "glyph"), "▲ 4 局");
  assert.equal(inningLabel(live, "text"), "上4局");

  const final = snapshot({ phase: "final", inning: 9, half: "2", event_count: 355 });
  assert.equal(inningLabel(final, "glyph"), "▼ 9 局");
  assert.equal(inningLabel(final, "text"), "下9局");
});

test("保留賽等非 live/final phase 以 event_count 認定是否已開打", () => {
  const played = snapshot({ phase: "reserved", inning: 5, half: "2", event_count: 180 });
  assert.equal(hasStartedPlay(played), true);
  assert.equal(inningLabel(played, "glyph"), "▼ 5 局");

  const rainedOut = snapshot({ phase: "postponed", inning: 1, half: "1", event_count: 0 });
  assert.equal(hasStartedPlay(rainedOut), false);
  assert.equal(inningLabel(rainedOut, "glyph"), null);
});

test("兩隊 lineup 可各自 partial，stale/error 不偽裝成未公布", () => {
  assert.equal(lineupMessage("announced", "fresh", "ok"), "已公布");
  assert.equal(lineupMessage("partial", "fresh", "ok"), "部分公布");
  assert.equal(lineupMessage("not_announced", "fresh", "ok"), "尚未公布");
  assert.equal(lineupMessage("announced", "stale", "ok"), "資料可能已過期（保留最近名單）");
  assert.equal(lineupMessage("announced", "fresh", "error"), "來源中斷（保留最近名單）");
});

// ── 官方既有欄位（LIVE-SNAPSHOT-FIELDS1）─────────────────────────────────
// fixture 為生產真實 payload。父卡與 FIX1 的漏網全出於手寫 mock 比真實資料更完整
// 更乾淨（自行補 ErrorCnt、把 RunBattedINCnt 拼成 RunBattedIncnt），
// 等於用對契約的想像驗證對契約的實作。

const realGame = JSON.parse(
  readFileSync(new URL("./__fixtures__/stats_game_2026-A-234.json", import.meta.url), "utf8"),
) as Record<string, never>;

// 把真實官方 payload 轉成 worker 產出的 snapshot 形狀（與 build_snapshot 對齊）
const realSnapshot = (overrides: Partial<LiveSnapshot> = {}): LiveSnapshot => {
  const g = realGame as Record<string, Record<string, never>>;
  const side = (key: "Visiting" | "Home") => {
    const s = g[key] as Record<string, never>;
    return {
      team: { code: (s.Team as Record<string, string>).Code, name: (s.Team as Record<string, string>).Name },
      score: Number(s.Score), hits: Number(s.HittingCnt), errors: Number(s.ErrorCnt),
      record: { w: null, l: null, t: null },
      inning_score: s.InningScore as unknown as Record<string, unknown>[],
      lineup: { availability: "announced" as const, items: [], first_observed_at: null },
      hitters: s.Hitters as unknown as Record<string, unknown>[],
      pitchers: s.Pitchers as unknown as Record<string, unknown>[],
      probable_pitcher: { availability: "not_announced" as const },
    };
  };
  const person = (k: string) => {
    const p = g[k] as unknown as { Acnt: string; Name: string; YearlyCount?: number } | undefined;
    if (!p?.Acnt) return null;
    return p.YearlyCount == null
      ? { player_id: p.Acnt, name: p.Name }
      : { player_id: p.Acnt, name: p.Name, yearly_count: p.YearlyCount };
  };
  return snapshot({
    phase: "final", raw_status: "FINISHED", inning: 9, half: "2",
    event_count: 260, away: side("Visiting"), home: side("Home"),
    decisions: {
      winning_pitcher: person("WinningPitcher"), losing_pitcher: person("LoserPitcher"),
      closer: person("Closer"), mvp: person("MVP"),
    },
    skip_trackman: false,
    ...overrides,
  });
};

/** 真實 stats payload → worker canonical 的逐球子集；不可另手寫官方欄位名稱。 */
const realLiveSnapshot = (mode: "available" | "empty" | "old" = "available"): LiveSnapshot => {
  const game = realGame as unknown as { LiveLog: Record<string, unknown>[] };
  const livelog = game.LiveLog.map((event) => {
    const raw = event.Trackman as Record<string, Record<string, Record<string, unknown>>> | null;
    const tag = raw?.Play?.PitchTag;
    const release = raw?.Pitch?.Release;
    const location = raw?.Pitch?.Location;
    const launch = raw?.Hit?.Launch;
    const landing = raw?.Hit?.LandingFlat;
    const row: Record<string, unknown> = {
      MainEventNo: event.MainEventNo, PitcherAcnt: event.PitcherAcnt, HitterAcnt: event.HitterAcnt,
      InningSeq: event.InningSeq, VisitingHomeType: event.VisitingHomeType,
      IsChangePlayer: event.IsChangePlayer, PitchCnt: event.PitchCnt,
      IsBall: event.IsBall, IsStrike: event.IsStrike, Content: event.Content,
    };
    if (mode !== "old") row.trackman = mode === "empty" || !raw ? null : {
      pitch_call: tag?.PitchCall ?? null, tagged_pitch_type: tag?.TaggedPitchType ?? null,
      rel_speed: release?.RelSpeed ?? null, plate_loc_side: location?.PlateLocSide ?? null,
      plate_loc_height: location?.PlateLocHeight ?? null, exit_speed: launch?.ExitSpeed ?? null,
      launch_angle: launch?.Angle ?? null, hit_spin_rate: launch?.HitSpinRate ?? null,
      hit_distance: landing?.Distance ?? null, hit_hang_time: landing?.HangTime ?? null,
    };
    return row;
  });
  return realSnapshot({
    phase: "live", raw_status: "START", freshness: "fresh",
    tracking_count: mode === "available" ? livelog.filter((row) => row.trackman).length : 0,
    livelog,
  });
};

test("真實官方 TrackMan fixture 在 live snapshot 產生逐球列；空、partial 與舊版均誠實降階", () => {
  const raw = (realGame as unknown as { LiveLog: Record<string, unknown>[] }).LiveLog;
  const rawTracked = raw.filter((row) => row.Trackman != null);
  assert.ok(rawTracked.length > 0, "fixture 必須含有官方 TrackMan 事件");

  const tracked = applyLiveSnapshot(response(realLiveSnapshot()));
  const tracking = tracked.tracking as {
    main_event_no: string; main_event_nos: string[]; rel_speed: number | null; pitch_call: string | null;
  }[];
  assert.equal(tracked.has_tracking, true);
  assert.equal(tracking.length, rawTracked.length);
  assert.equal(tracking[0].main_event_no, String(rawTracked[0].MainEventNo));
  assert.equal(tracking[0].rel_speed, (rawTracked[0].Trackman as { Pitch: { Release: { RelSpeed: number } } }).Pitch.Release.RelSpeed);
  // fixture 的首打席有五顆官方 TrackMan 球；點末球也必須取回整個打席，不能只剩選中那顆。
  const firstPa = tracking.filter((pitch) => pitch.main_event_nos.includes("0110005000"));
  assert.equal(firstPa.length, 5);
  assert.ok(firstPa.every((pitch) => pitch.main_event_nos.length === 5));
  assert.deepEqual(
    tracking.slice(0, 5).map((pitch) => pitch.pitch_call),
    ["FoulBallNotFieldable", "BallCalled", "StrikeSwinging", "BallCalled", "StrikeCalled"],
    "TrackMan 尚無 PitchCall 時，應以真實官方 IsBall／IsStrike／Content 顯示判決",
  );

  for (const mode of ["empty", "old"] as const) {
    const degraded = applyLiveSnapshot(response(realLiveSnapshot(mode)));
    assert.equal(degraded.has_tracking, false, `${mode} snapshot 不得捏造逐球資料`);
    assert.deepEqual(degraded.tracking, [], `${mode} snapshot 不得產生猜測 mapping`);
  }
});

test("官方 live 判決不完整時 fail-closed，不猜測好壞球", () => {
  assert.equal(officialLivePitchCall({ IsBall: "1", IsStrike: "0", Content: "壞球。" }, null), "BallCalled");
  assert.equal(officialLivePitchCall({ IsBall: "0", IsStrike: "1", Content: "好球沒揮棒。" }, null), "StrikeCalled");
  assert.equal(officialLivePitchCall({ IsBall: "0", IsStrike: "1", Content: "擊出界外球。" }, null), "FoulBallNotFieldable");
  assert.equal(officialLivePitchCall({ IsBall: "0", IsStrike: "0", Content: "換投。" }, null), null);
});

test("擊出球展開使用原生 button、可讀名稱與 44px 觸控目標", () => {
  const board = readFileSync(new URL("../components/game-board.tsx", import.meta.url), "utf8");
  assert.match(board, /<button type="button"[^>]*min-h-11 min-w-11/);
  assert.match(board, /aria-label=.*擊出球數據/);
  assert.match(board, /aria-controls=/);
});

test("記分板 H/E 取官方隊伍層級真值；E 不再恆為 0", () => {
  const out = applyLiveSnapshot(response(realSnapshot()));
  assert.equal(out.game?.away_hits, 7);
  assert.equal(out.game?.home_hits, 7);
  assert.equal(out.game?.away_errors, 0);
  assert.equal(out.game?.home_errors, 1);   // 官方 Home.ErrorCnt=1，畫面曾印 0
  // 逐局 H/E 仍為 unknown（stats 站不供），不得由總計回填
  assert.ok(out.scoreboard.every((r) => r.hitting_cnt === null && r.error_cnt === null));
});

test("官方未供 H/E 時保持 null，不得回退成 0", () => {
  const bare = snapshot({ away: { ...snapshot().away, hits: null, errors: null, hitters: [] } });
  const out = applyLiveSnapshot(response(bare));
  assert.equal(out.game?.away_hits, null);
  assert.equal(out.game?.away_errors, null);
});

test("DB 未補資料時決勝改由 snapshot 供，有 DB 值則不倒退", () => {
  const out = applyLiveSnapshot(response(realSnapshot()));
  assert.equal(out.decisions?.["0000006906"], "W");   // 艾菩樂
  assert.equal(out.decisions?.["0000005731"], "L");   // 布雷克
  assert.equal(out.decisions?.["0000000941"], "SV");  // 陳冠宇

  const withDb = response(realSnapshot());
  withDb.decisions = { "9999999999": "W" };
  assert.deepEqual(applyLiveSnapshot(withDb).decisions, { "9999999999": "W" });
});

test("決勝資訊列所需的 game.*_id 與 people 也由 snapshot 補上", () => {
  const out = applyLiveSnapshot(response(realSnapshot()));
  assert.equal(out.game?.winning_pitcher_id, "0000006906");
  assert.equal(out.game?.losing_pitcher_id, "0000005731");
  assert.equal(out.game?.closer_id, "0000000941");
  assert.equal(out.game?.mvp_id, "0000006906");
  assert.equal(out.people["0000006906"], "艾菩樂");
  assert.equal(out.people["0000005731"], "布雷克");

  // DB 有決勝時不得由 snapshot 覆寫
  const withDb = response(realSnapshot());
  withDb.decisions = { "9999999999": "W" };
  const dbOut = applyLiveSnapshot(withDb);
  assert.equal(dbOut.game?.winning_pitcher_id, undefined);
});

test("MVP 由 snapshot 補 box 旗標與本季次數，DB 有值時不覆寫", () => {
  const out = applyLiveSnapshot(response(realSnapshot()));
  const mvpRow = out.pitching.find((r) => r.is_mvp) ?? out.batting.find((r) => r.is_mvp);
  assert.ok(mvpRow, "應在 box 列標出 MVP");
  assert.equal(String(mvpRow!.pitcher_acnt ?? mvpRow!.hitter_acnt), "0000006906");
  assert.equal((out.decision_counts as { mvp?: number }).mvp, 1);

  const withDb = response(realSnapshot());
  withDb.decisions = { "9999999999": "W" };
  const dbOut = applyLiveSnapshot(withDb);
  assert.equal(dbOut.batting.some((r) => r.is_mvp), false);
  assert.equal(dbOut.pitching.some((r) => r.is_mvp), false);
});

test("打點／觸身／盜壘的 alias 對得上真實欄位（曾整欄空白）", () => {
  const out = applyLiveSnapshot(response(realSnapshot()));
  const row = out.batting.find((r) => Number(r.at_bats) > 0)!;
  for (const key of ["rbi", "hbp", "sb"]) {
    assert.ok(key in row, `${key} 未由 alias 映射出來`);
  }
});

test("TrackMan 可用性以官方 skip_trackman 判定，未知不得說成沒有設備", () => {
  assert.equal(trackmanAvailability(null), "unknown");
  assert.equal(trackmanAvailability(snapshot()), "unknown");           // 舊 snapshot 無此欄位
  assert.equal(trackmanAvailability(snapshot({ skip_trackman: false })), "expected");
  assert.equal(trackmanAvailability(snapshot({ skip_trackman: true })), "unavailable");

  assert.ok(!/未配置|未設置/.test(trackingPendingMessage(snapshot())));
  assert.match(trackingPendingMessage(snapshot({ skip_trackman: true })), /未配置/);
});

// LIVE-SNAPSHOT-FIELDS1-F1（查核退回）：完賽且無逐球資料時，先前所有入口都硬編
// 「球場未設置 TrackMan 設備」，即使 snapshot 明確 skip_trackman=false 也照講。
// 三態必須分流，且只有 true 可宣稱未配置。
test("完賽空狀態依 skip_trackman 三態分流，false/null 不得宣稱未配置設備", () => {
  const finalWith = (skip: boolean | null) =>
    snapshot({ phase: "final", freshness: "final", ...(skip === null ? {} : { skip_trackman: skip }) });

  // true：唯一可以說未配置的情況
  const unavailable = trackingEmptyMessage(finalWith(true), "無擊球落點圖");
  assert.match(unavailable, /未配置/);
  assert.match(unavailable, /無擊球落點圖/);

  // false：場地有設備，只是尚未發布——不得說未配置
  const expected = trackingEmptyMessage(finalWith(false), "無主審判決分布");
  assert.doesNotMatch(expected, /未配置|未設置/);
  assert.match(expected, /尚未發布/);
  assert.match(expected, /無主審判決分布/);

  // null（舊 snapshot 或無 snapshot）：不得推測原因
  for (const s of [finalWith(null), null]) {
    const unknown = trackingEmptyMessage(s, "無擊球落點圖");
    assert.doesNotMatch(unknown, /未配置|未設置|尚未發布/);
    assert.match(unknown, /無逐球追蹤資料/);
  }
});

test("賽中三態：skip_trackman=true 仍講未配置，其餘走整理中文案", () => {
  assert.match(trackingEmptyMessage(snapshot({ skip_trackman: true }), "X"), /未配置/);
  assert.match(trackingEmptyMessage(snapshot({ skip_trackman: false }), "X"), /賽中逐球追蹤尚在整理/);
  assert.match(trackingEmptyMessage(snapshot(), "X"), /賽中逐球追蹤尚在整理/);
});

test("spray chart 與 umpire tab 的完賽空狀態都改走 trackingEmptyMessage", () => {
  const boxTabs = readFileSync(new URL("../app/games/[sno]/box-tabs.tsx", import.meta.url), "utf8");
  assert.match(boxTabs, /trackingEmptyMessage\(data\.live_snapshot \?\? null, "無擊球落點圖"\)/);
  assert.match(boxTabs, /trackingEmptyMessage\(data\.live_snapshot \?\? null, "無主審判決分布"\)/);
  const board = readFileSync(new URL("../components/game-board.tsx", import.meta.url), "utf8");
  assert.match(board, /trackingEmptyMessage\(data\.live_snapshot \?\? null/);
  // 三個檔案都不得再出現硬編的設備結論
  for (const src of [boxTabs, board]) {
    assert.doesNotMatch(src, /未設置 TrackMan|未設置 TrackMan 的球場/);
  }
});
