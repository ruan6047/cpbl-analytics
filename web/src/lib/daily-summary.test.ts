import assert from "node:assert/strict";
import test from "node:test";

import {
  resolvePregameFromDaily,
  pregameServingNotice,
  homePregameNotice,
  refreshCopy,
  refreshAtText,
  taipeiParts,
  taipeiTime,
  shortDate,
  slateDistanceText,
  gameHref,
  REFRESH_COPY,
  dailySummaryQuery,
  liveAgeSeconds,
  liveInterrupt,
  liveSourceSignal,
  officialFactLine,
  phaseTone,
  showTodaySlate,
  sortTodayGames,
  todayCardKind,
  todayInningLabel,
  todayGameSettled,
  todayPollDelayMs,
  todayStatusText,
  latestGameStatus,
  latestGameDateNote,
  latestDayPendingCount,
  LATEST_STATUS_COPY,
  LATEST_FOOTER_COPY,
  TODAY_COPY,
  TODAY_POLL_LIVE_MS,
  TODAY_POLL_PREGAME_MS,
  type DailyGame,
  type DailyGamePregame,
  type DailySummary,
  type RefreshStatus,
  type TodayGame,
  type TodayLive,
  type TodaySlate,
} from "./daily-summary.ts";

// —— PregameCard adapter：daily summary 內嵌 pregame → 五態，永不 throw、永不造 50% ——

const availablePregame: DailyGamePregame = {
  status: "available",
  home_win_probability: 0.62,
  signals: {
    suppression: { key: "starter_era_diff", raw: -0.8, direction: "lower_favors_home" },
    strength: { key: "winrate_diff", raw: 0.1, direction: "higher_favors_home" },
  },
};

test("available pregame 解出點機率＋主訊號，無區間欄位", () => {
  const m = resolvePregameFromDaily(availablePregame, 2025);
  assert.equal(m.status, "available");
  if (m.status !== "available") return;
  assert.equal(m.homeWinProbability, 0.62);
  assert.equal(m.probabilityText, "62%");
  assert.ok(m.primarySignal, "應挑出主訊號");
  assert.equal(m.primarySignal?.key, "starter_era_diff"); // suppression 群優先
  assert.equal(m.primarySignal?.favors, "home"); // raw<0 且 lower_favors_home → 利主隊
  assert.equal(m.trainedThroughText, "模型資料至 2025 季");
  assert.ok(!("model_interval_90" in m), "卡片模型不得帶區間欄位");
});

test("available 但機率為 null → pending（不補 50%）", () => {
  const m = resolvePregameFromDaily(
    { status: "available", home_win_probability: null, signals: null },
    2025,
  );
  assert.equal(m.status, "pending");
});

test("五種缺席狀態各自對映，且都不是 available", () => {
  assert.equal(resolvePregameFromDaily({ status: "artifact_missing", home_win_probability: null, signals: null }, null).status, "missing_artifact");
  assert.equal(resolvePregameFromDaily({ status: "no_features", home_win_probability: null, signals: null }, null).status, "pending");
  assert.equal(resolvePregameFromDaily({ status: "unsupported", home_win_probability: null, signals: null }, null).status, "unsupported");
  assert.equal(resolvePregameFromDaily({ status: "error", home_win_probability: null, signals: null }, null).status, "error");
});

test("缺 pregame 欄位（latest 場次或二軍）→ unsupported，不擲錯", () => {
  assert.equal(resolvePregameFromDaily(undefined, null).status, "unsupported");
  assert.equal(resolvePregameFromDaily(null, 2025).status, "unsupported");
});

// —— freshness 文案：各 status 分立（§8.1 不得共用同一句）——

test("五個 refresh status 的文案兩兩不同", () => {
  const statuses: RefreshStatus[] = ["fresh", "stale", "failed", "unknown", "source_error"];
  const labels = statuses.map((s) => refreshCopy(s).label);
  assert.equal(new Set(labels).size, labels.length, "freshness 文案不得共用");
});

test("refreshCopy 未知值退回 unknown 文案", () => {
  assert.equal(refreshCopy("bogus" as RefreshStatus).label, REFRESH_COPY.unknown.label);
});

test("刷新時刻用絕對時間，不用「N 小時前」", () => {
  // 排程是每日 10:10 一班，所以隔天清晨「20 小時前」是完全正常的狀態，卻與旁邊
  // 「資料為最新」讀起來互相矛盾；而那個數字幾乎永遠很大，大到多少都不代表任何事。
  // 維護者要回答的是「今天那班跑了沒」——是非題，不是時數。
  assert.equal(refreshAtText("2026-08-07T02:12:00+00:00", "2026-08-07"), "今日 10:12 刷新");
  assert.equal(refreshAtText("2026-08-06T02:12:00+00:00", "2026-08-07"), "昨日 10:12 刷新");
  // 更早的日期不再用「N 天前」，直接給日期——落後多久由旁邊的 status 徽章負責表達。
  assert.equal(refreshAtText("2026-08-05T02:12:00+00:00", "2026-08-07"), "08/05 10:12 刷新");
  assert.equal(refreshAtText(null, "2026-08-07"), null);
  assert.equal(refreshAtText("garbage", "2026-08-07"), null);
});

test("**紅線**：刷新時刻釘死台北時區，不吃執行環境時區", () => {
  // 本專案容器沒設 TZ（python:slim 與 node 皆預設 UTC），瀏覽器是台北。用預設時區
  // 格式化會讓 SSR 與 hydration 印出不同字串——LiveCard 曾為此改成掛載後才渲染。
  const iso = "2026-08-07T02:12:00+00:00";     // ＝台北 10:12
  assert.deepEqual(taipeiParts(iso), { date: "2026-08-07", time: "10:12" });
  assert.equal(taipeiTime(iso), "10:12");

  // 同一瞬間、不同寫法必須得到同一個台北時刻（證明吃的是瞬間而非字串上的時區）。
  assert.equal(taipeiTime("2026-08-07T10:12:00+08:00"), "10:12");
  assert.equal(taipeiTime("2026-08-06T22:12:00-04:00"), "10:12");

  // 跨日界：UTC 前一天的深夜＝台北的隔天清晨，今日／昨日必須依台北曆日判定。
  assert.equal(refreshAtText("2026-08-06T20:30:00+00:00", "2026-08-07"), "今日 04:30 刷新");
  assert.equal(taipeiTime(null), null);
  assert.equal(taipeiParts("garbage"), null);
});

// —— 一般 helper ——

test("shortDate 取 MM/DD；null/非法原樣或破折號", () => {
  assert.equal(shortDate("2026-07-16"), "07/16");
  assert.equal(shortDate(null), "—");
  assert.equal(shortDate("garbage"), "garbage");
});

test("slateDistanceText 不寫死今天／明天，改以天數距離", () => {
  assert.equal(slateDistanceText(0), "即將開打");
  assert.equal(slateDistanceText(1), "隔日賽事");
  assert.equal(slateDistanceText(3), "3 天後");
});

test("gameHref 對齊 /games 既有查詢字串", () => {
  assert.equal(
    gameHref({ game_sno: 117, kind_code: "A", season: 2026 }),
    "/games/117?kind=A&year=2026",
  );
});

// —— serving 降級揭露（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）——

test("serving_current 不出告示：正常狀態不得製造噪音", () => {
  assert.equal(
    pregameServingNotice({
      status: "serving_current",
      serving_version: "v2",
      backtest_version: "v2",
    }),
    null,
  );
});

test("gate_failed：唯一能宣稱閘門失敗的成因", () => {
  const notice = pregameServingNotice({
    status: "serving_previous",
    degradation: "gate_failed",
    serving_version: "outcome-simple-1",
    backtest_version: "outcome-simple-2",
    backtest_deployable: false,
  });

  assert.ok(notice);
  assert.ok(notice.includes("未通過部署閘門"));
  assert.ok(notice.includes("outcome-simple-1"), "必須指名 serving 中的版本");
  assert.ok(notice.includes("outcome-simple-2"), "必須指名最新回測版本");
});

test("version_mismatch：回測其實通過了閘門，不得講成閘門失敗", () => {
  const notice = pregameServingNotice({
    status: "serving_previous",
    degradation: "version_mismatch",
    serving_version: "outcome-simple-3",
    backtest_version: "outcome-simple-2",
    backtest_deployable: true,
  });

  assert.ok(notice);
  assert.equal(notice.includes("未通過部署閘門"), false, "回測已通過，不得宣稱閘門失敗");
  assert.ok(notice.includes("不一致"));
  assert.ok(notice.includes("已通過閘門"));
});

test("version_unknown：deploy→refresh 窗口的實際狀態，只能說無法確認", () => {
  // prod 現行 artifact 沒有 version 欄，而最新回測是 7/7 通過的——iteration 2 會在這裡
  // 宣稱「最新回測未通過部署閘門」，正好在唯一會被看到的窗口說錯話。
  const notice = pregameServingNotice({
    status: "serving_previous",
    degradation: "version_unknown",
    serving_version: null,
    backtest_version: "outcome-simple-2",
    backtest_deployable: true,
  });

  assert.ok(notice);
  assert.equal(notice.includes("未通過部署閘門"), false, "不得誣賴一個通過的回測");
  assert.ok(notice.includes("無法確認"));
  assert.ok(notice.includes("outcome-simple-2"));
});

test("serving_gate_failed：status 是 serving_current 也一定要揭露（開關是 degradation）", () => {
  // iteration 6 查核 F1：版本相同時 deployable=false 被整個蓋掉，畫面毫無提示照顯機率。
  const notice = pregameServingNotice({
    status: "serving_current",
    degradation: "serving_gate_failed",
    serving_version: "outcome-simple-2",
    backtest_version: "outcome-simple-2",
    backtest_deployable: false,
  });

  assert.ok(notice, "status 正常不代表可以靜默");
  assert.ok(notice.includes("未通過部署閘門"));
  assert.ok(notice.includes("outcome-simple-2"));
  // 這一版就是正在服務的模型，講「沿用上一版」或「並非最新回測的輸出」都是假話。
  assert.equal(notice.includes("沿用"), false);
  assert.equal(notice.includes("並非最新回測"), false);
});

test("serving_current 且無 degradation 時仍然不出告示", () => {
  assert.equal(
    pregameServingNotice({
      status: "serving_current",
      degradation: null,
      serving_version: "v2",
      backtest_version: "v2",
      backtest_deployable: true,
    }),
    null,
  );
});

test("首頁：serving_gate_failed 同樣要揭露", () => {
  const notice = homePregameNotice(
    summaryWith({
      status: "serving_current",
      reason: "最新回測未通過部署閘門，而 serving 就是該次回測產出的模型",
      degradation: "serving_gate_failed",
      serving_version: "outcome-simple-2",
      backtest_version: "outcome-simple-2",
      backtest_deployable: false,
      trained_through: 2025,
      signals: null,
    }),
  );

  assert.ok(notice, "首頁不得因為 status=serving_current 就靜默");
  assert.ok(notice.includes("未通過部署閘門"));
  assert.equal(notice.includes("沿用"), false);
});

test("gate_failed 與 serving_gate_failed 的說法不可互換", () => {
  const base = {
    status: "serving_previous" as const,
    serving_version: "outcome-simple-1",
    backtest_version: "outcome-simple-2",
    backtest_deployable: false,
  };
  const previous = pregameServingNotice({ ...base, degradation: "gate_failed" });
  const current = pregameServingNotice({
    ...base,
    status: "serving_current",
    serving_version: "outcome-simple-2",
    degradation: "serving_gate_failed",
  });

  assert.ok(previous && current);
  assert.notEqual(previous, current);
  // 沿用上一版 vs 正在服務那一版——兩件不同的事，各自只講自己那件。
  assert.ok(previous.includes("沿用"));
  assert.equal(current.includes("沿用"), false);
});

test("version_mismatch 但 backtest_deployable 非 true：不得附註「已通過閘門」", () => {
  // 後端保證這條分支必為 true，但前端不靠那個保證說出 PASS——判別碼可能出錯，
  // backtest_deployable 才是這句話唯一的直接證據（iteration 5 查核 F1）。
  for (const deployable of [null, false, undefined] as const) {
    const notice = pregameServingNotice({
      status: "serving_previous",
      degradation: "version_mismatch",
      serving_version: "outcome-simple-3",
      backtest_version: "outcome-simple-2",
      backtest_deployable: deployable,
    });

    assert.ok(notice);
    assert.equal(notice.includes("已通過閘門"), false, `deployable=${deployable} 不得宣稱通過`);
    assert.equal(notice.includes("未通過部署閘門"), false, "也不得反過來宣稱失敗");
    assert.ok(notice.includes("不一致"));
  }
});

test("backtest_unknown：讀不到回測閘門結果時，文案不得出現任何閘門通過／失敗宣稱", () => {
  // 首頁與方法頁共用這支函式（方法頁自 @/lib/daily-summary 匯入同一個 symbol）。
  const notice = pregameServingNotice({
    status: "serving_previous",
    degradation: "backtest_unknown",
    serving_version: "outcome-simple-3",
    backtest_version: "outcome-simple-2",
    backtest_deployable: null,
  });

  assert.ok(notice);
  assert.equal(notice.includes("通過"), false, "未知就是未知，不得宣稱通過或未通過");
  assert.ok(notice.includes("無法確認"));
  assert.ok(notice.includes("outcome-simple-3"), "仍須指名正在 serving 的版本");
});

test("未知判別碼走中性文案：新增成因時最壞是講得籠統，不是被誤述成別的成因", () => {
  const notice = pregameServingNotice({
    status: "serving_previous",
    // 模擬後端新增了一個前端還不認識的判別碼。
    degradation: "some_future_code" as never,
    serving_version: "outcome-simple-3",
    backtest_version: "outcome-simple-2",
    backtest_deployable: true,
  });

  assert.ok(notice);
  assert.equal(notice.includes("通過"), false);
  assert.equal(notice.includes("未記錄版本"), false, "不得再沿用 version_unknown 的文案");
  assert.ok(notice.includes("無法確認"));
});

test("degradation 缺席時同樣走中性文案，不得冒充 version_unknown", () => {
  const notice = pregameServingNotice({
    status: "serving_previous",
    serving_version: "outcome-simple-3",
    backtest_version: "outcome-simple-2",
  });

  assert.ok(notice);
  assert.equal(notice.includes("未記錄版本"), false);
  assert.equal(notice.includes("通過"), false);
});

test("首頁：backtest_unknown 一樣要揭露，且不得宣稱閘門結果", () => {
  const notice = homePregameNotice(
    summaryWith({
      status: "serving_previous",
      reason: "無法確認最新回測的閘門結果（紀錄讀不到或未記載）",
      degradation: "backtest_unknown",
      serving_version: "outcome-simple-3",
      backtest_version: "outcome-simple-2",
      backtest_deployable: null,
      trained_through: 2025,
      signals: null,
    }),
  );

  assert.ok(notice, "讀不到回測時仍在顯示機率，必須揭露");
  assert.equal(notice.includes("通過"), false);
});

test("unavailable 不走告示：整段不可用由卡片自己的不可用文案負責", () => {
  assert.equal(
    pregameServingNotice({
      status: "unavailable",
      serving_version: null,
      backtest_version: null,
    }),
    null,
  );
});

// —— 跨 response 競態：機率與 serving 狀態必須同源（ML-OUTCOME-SIMPLE-LEAK2 it.3 缺陷）——

/** 只帶本測試在意的欄位；其餘欄位對告示判定無影響。 */
function summaryWith(pregameModel: Record<string, unknown>): DailySummary {
  return {
    scope: { season: null, kind_code: "A", kinds: ["A"], as_of: "2026-07-27" },
    latest_game_day: null,
    next_slate: {
      game_date: "2026-07-28",
      days_from_as_of: 1,
      games: [{ pregame: { status: "available", home_win_probability: 0.61, signals: null } }],
    },
    freshness: {
      as_of: "2026-07-27",
      last_completed_game_date: null,
      last_refresh: { at: null, ok: null, scope: null, hours_ago: null, status: "unknown", reason: null },
      unresolved_games: [],
    },
    availability: {
      schedule: { status: "available", reason: null },
      results: { status: "available", reason: null },
      pregame_model: pregameModel,
    },
  } as unknown as DailySummary;
}

test("競態重現：快取的舊機率 ＋ 即時 serving_current，不得靜默顯示舊機率", () => {
  // 時序：1) 首頁快取了舊模型的機率，內嵌狀態 version_unknown
  //       2) refresh 完成，artifact/DB 晉升 v2
  //       3) 重新請求——舊寫法會拿到 cached 機率配 live 的「一切正常」
  const cachedSummary = summaryWith({
    status: "serving_previous",
    reason: "serving artifact 未記錄版本（去洩漏前的舊格式）",
    degradation: "version_unknown",
    serving_version: null,
    backtest_version: "outcome-simple-1",
    backtest_deployable: true,
    trained_through: 2025,
    signals: null,
  });
  const liveServingAfterRefresh = {
    status: "serving_current" as const,
    serving_version: "outcome-simple-2",
    backtest_version: "outcome-simple-2",
    backtest_deployable: true,
    degradation: null,
  };

  // 舊寫法（無條件優先 live）會讓告示消失——缺陷本體：
  assert.equal(pregameServingNotice(liveServingAfterRefresh), null);

  // 新寫法只認產生這些機率的那一份 response，因此告示仍在：
  const notice = homePregameNotice(cachedSummary);
  assert.ok(notice, "顯示某一份 response 的機率時，必須顯示同一份 response 的降級狀態");
  assert.ok(notice.includes("無法確認"));

  // 且 homePregameNotice 的簽章只收 summary——結構上無從再接第二個來源。
  assert.equal(homePregameNotice.length, 1);
});

test("同一份 response 顯示 serving_current 時才可以沒有告示", () => {
  const fresh = summaryWith({
    status: "serving_current",
    reason: null,
    degradation: null,
    serving_version: "outcome-simple-2",
    backtest_version: "outcome-simple-2",
    backtest_deployable: true,
    trained_through: 2025,
    signals: null,
  });

  assert.equal(homePregameNotice(fresh), null);
});

// —— 今日賽事三態（UX-HOME-LIVE-STRIP1）——
//
// 卡面點名的十種情境，逐一在此以純函式覆蓋（後端側在 `tests/test_daily_summary.py`）：
// 今天無場次／賽前未達 lineup／任一場 lineup 觸發切換／單場 live／三場 live／
// stale 一階／stale 二階／worker 不可用／final 當晚／跨日回退。

const T0 = Date.parse("2026-08-07T19:30:00+08:00");

function live(over: Partial<TodayLive> = {}): TodayLive {
  return {
    phase: "live",
    raw_status: "START",
    starts_at: "2026-08-07T18:35:00+08:00",
    inning: 5,
    half: "2",
    outs: 1,
    bases: { first: true, second: false, third: false },
    away_score: 2,
    home_score: 3,
    event_count: 150,
    freshness: "fresh",
    stale_after_seconds: 45,
    source_status: "ok",
    fetched_at: new Date(T0 - 10_000).toISOString(),
    interrupt: "none",
    decisions: null,
    ...over,
  };
}

function game(sno: number, over: Partial<TodayGame> = {}): TodayGame {
  return {
    season: 2026, kind_code: "A", game_sno: sno, game_date: "2026-08-07", venue: "洲際",
    away_team_code: "ADD011", away_team_name: "統一7-ELEVEn獅", away_score: null,
    home_team_code: "ACN011", home_team_name: "中信兄弟", home_score: null,
    completed: false, delay_kind: null, orig_date: null, live: null,
    ...over,
  } as TodayGame;
}

function slate(games: TodayGame[], over: Partial<TodaySlate> = {}): TodaySlate {
  const snapshots = games.filter((g) => g.live !== null).length;
  return {
    game_date: "2026-08-07",
    started: games.some((g) => g.completed
      || ["lineup_announced", "live", "final"].includes(g.live?.phase ?? "")),
    live_source: { status: snapshots === games.length ? "ok" : snapshots ? "partial" : "unavailable",
                   reason: null, snapshots, games: games.length },
    games,
    ...over,
  };
}

function summaryOf(today: TodaySlate | null): DailySummary {
  return { ...summaryWith({ status: "serving_current", degradation: null }), today };
}

test("情境1｜今天無場次：today 為 null → 退回最近比賽日＋下一批賽事", () => {
  assert.equal(showTodaySlate(summaryOf(null)), false);
  assert.equal(todayPollDelayMs(null), null, "沒有今日場次時零 polling");
});

test("情境2｜賽前未達 lineup：主位維持上一個比賽日", () => {
  const s = slate([game(247, { live: live({ phase: "scheduled", inning: null, bases: null }) }),
                   game(248, { live: live({ phase: "probable_announced", inning: null, bases: null }) })]);
  assert.equal(s.started, false);
  assert.equal(showTodaySlate(summaryOf(s)), false);
  // 但今天仍有會變的場次 → 必須輪詢，否則打線公布永遠翻不了頁。
  assert.equal(todayPollDelayMs(s), TODAY_POLL_PREGAME_MS);
});

test("情境3｜任一場 lineup_announced 即切換；單邊公布也算（phase 已是任一隊判準）", () => {
  const s = slate([game(247, { live: live({ phase: "scheduled", inning: null, bases: null }) }),
                   game(248, { live: live({ phase: "lineup_announced", inning: null, bases: null }) })]);
  assert.equal(showTodaySlate(summaryOf(s)), true);
  // 打線公布仍是**賽前態**：賽前卡不得被收掉。
  assert.equal(todayCardKind(s.games[1]), "pregame");
});

test("情境4｜單場 live：卡片為賽中態，輪詢 20 秒", () => {
  const s = slate([game(247, { live: live() }), game(248, { live: live({ phase: "lineup_announced" }) })]);
  assert.equal(todayCardKind(s.games[0]), "live");
  assert.equal(todayPollDelayMs(s), TODAY_POLL_LIVE_MS);
  assert.equal(todayInningLabel(s.games[0].live!, "glyph"), "▼ 5 局");
  assert.equal(todayInningLabel(s.games[0].live!, "text"), "下5局");
});

test("情境5｜三場 live：全部顯示，不截斷、不摺疊", () => {
  const s = slate([247, 248, 249].map((sno) => game(sno, { live: live() })));
  assert.equal(sortTodayGames(s.games).length, 3);
  assert.equal(s.games.every((g) => todayCardKind(g) === "live"), true);
});

test("情境6｜stale 一階：保留數字，只加中斷標示", () => {
  const l = live({ fetched_at: new Date(T0 - 60_000).toISOString(), freshness: "stale" });
  assert.equal(liveInterrupt(l, T0), "degraded");
  assert.ok(todayStatusText(l, "degraded")?.includes(TODAY_COPY.interrupted));
});

test("情境7｜stale 二階：超過門檻→ blackout（呈現端據此收掉所有會變的數字）", () => {
  const l = live({ fetched_at: new Date(T0 - 200_000).toISOString(), freshness: "stale" });
  assert.equal(liveInterrupt(l, T0), "blackout");
  assert.ok(todayStatusText(l, "blackout")?.includes(TODAY_COPY.blackout));
});

test("兩階門檻的邊界：45 秒內正常、45～180 秒一階、180 秒後二階", () => {
  const at = (ageSec: number) => liveInterrupt(
    live({ fetched_at: new Date(T0 - ageSec * 1000).toISOString() }), T0);
  assert.equal(at(44), "none");
  assert.equal(at(46), "degraded");
  assert.equal(at(179), "degraded");
  assert.equal(at(181), "blackout");
});

test("**紅線**：fetched_at 缺席＝無從證明新鮮 → fail closed 收掉數字", () => {
  assert.equal(liveAgeSeconds(live({ fetched_at: null }), T0), null);
  assert.equal(liveInterrupt(live({ fetched_at: null }), T0), "blackout");
});

test("**紅線**：首屏（nowMs=null）吃後端算好的那一格，不碰瀏覽器時鐘", () => {
  // 首屏不能用瀏覽器時鐘（SSR 與 hydration 會畫出不同的卡），但也不該先亮出十分鐘前
  // 的比分再等一個輪詢週期才收掉——所以後端把分級一起送過來。
  const dead = live({ fetched_at: new Date(T0 - 600_000).toISOString(),
                      freshness: "stale", interrupt: "blackout" });
  assert.equal(liveInterrupt(dead, null), "blackout");
  assert.equal(liveInterrupt(live(), null), "none");
});

test("兩份判定取較嚴重者：輪詢打不出去時只有瀏覽器時鐘會繼續走", () => {
  // 後端那一格凍在最後一次成功的回應（none），瀏覽器時鐘已經走過門檻。
  const frozen = live({ fetched_at: new Date(T0 - 400_000).toISOString(), interrupt: "none" });
  assert.equal(liveInterrupt(frozen, T0), "blackout");
  // 反向：瀏覽器時鐘看起來很新，但後端說已經中斷 → 仍以後端為準。
  const skewed = live({ interrupt: "blackout" });
  assert.equal(liveInterrupt(skewed, T0), "blackout");
});

test("final 是不可變快照：不因時間經過被誤標中斷", () => {
  const done = live({ phase: "final", freshness: "final", stale_after_seconds: null,
                      fetched_at: new Date(T0 - 86_400_000).toISOString() });
  assert.equal(liveInterrupt(done, T0), "none");
});

test("賽前場次不套 3 分鐘黑幕（後端門檻是 20 分鐘，且卡上沒有會變的數字）", () => {
  const pre = live({ phase: "lineup_announced", inning: null, bases: null, outs: null,
                     stale_after_seconds: 1200,
                     fetched_at: new Date(T0 - 300_000).toISOString() });
  assert.equal(liveInterrupt(pre, T0), "none");
});

test("情境8｜worker 不可用：全場無 snapshot → started 為假、退回純日期版面", () => {
  const s = slate([game(247), game(248)]);
  assert.equal(s.started, false);
  assert.equal(showTodaySlate(summaryOf(s)), false);
  assert.equal(s.games.every((g) => todayCardKind(g) === "pregame"), true);
  // 維護者訊號進 freshness 條；訪客面不宣稱即時。
  assert.equal(liveSourceSignal(s).kind, "down");
  assert.equal(liveSourceSignal(s).tone, "warn");
});

// —— 裁決 B｜freshness 條的即時來源四態 ——

test("裁決B｜「今天沒有場次」與「今日即時來源不可用」必須是兩種不同的訊號", () => {
  // 這兩種情形在**訪客面完全同形**（都退回純日期版面）。維護者要能一眼分出
  // 「不需要做事」與「即時管道斷了」，只能靠這一格。
  const restDay = liveSourceSignal(null);
  const sourceDown = liveSourceSignal(slate([game(247), game(248), game(249)]));

  assert.equal(restDay.kind, "no_games");
  assert.equal(sourceDown.kind, "down");
  assert.notEqual(restDay.label, sourceDown.label);
  assert.notEqual(restDay.tone, sourceDown.tone);
  // 休兵日是正常狀態，不得用警示色叫人去看東西。
  assert.equal(restDay.tone, "scheduled");
  assert.equal(sourceDown.tone, "warn");
});

test("裁定4｜正常態壓縮成符號，但語意不縮水（完整句仍在 aria-label／title）", () => {
  const allGood = liveSourceSignal(slate([game(247, { live: live() })]));

  assert.equal(allGood.kind, "ok");
  assert.equal(allGood.display, "symbol");
  assert.ok(allGood.symbol, "符號態必須給得出要畫的字元");
  assert.ok(allGood.label, "完整語意不得消失——它要進 aria-label／title");
  // 四態一定回得出一格，呈現端因此可以恆常渲染，不必自己判斷要不要留位子。
  for (const t of [null, slate([game(247)]), slate([game(247, { live: live() })]),
                   slate([game(247, { live: live() }), game(248)])]) {
    assert.ok(liveSourceSignal(t).label);
  }
});

test("裁定4｜**只有**「一切正常」壓縮成符號；其餘三態維持完整文字", () => {
  // 被壓縮的必須是「不需要行動」那一態。今日無賽程維持文字（它解釋版面為何是舊雙塊）、
  // 兩個異常態維持完整文字＋警示色，否則要人去看即時管道的訊號會被縮成一個小圖示。
  const byKind = Object.fromEntries([
    liveSourceSignal(null),
    liveSourceSignal(slate([game(247, { live: live() })])),
    liveSourceSignal(slate([game(247, { live: live() }), game(248)])),
    liveSourceSignal(slate([game(247), game(248), game(249)])),
  ].map((x) => [x.kind, x]));

  assert.equal(byKind.ok.display, "symbol");
  assert.equal(byKind.no_games.display, "badge");
  assert.equal(byKind.partial.display, "badge");
  assert.equal(byKind.down.display, "badge");
  assert.deepEqual([byKind.partial.tone, byKind.down.tone], ["warn", "warn"]);
});

test("裁決B｜四態文案兩兩不同（§8.1：不同語意不共用同一句）", () => {
  const signals = [
    liveSourceSignal(null),
    liveSourceSignal(slate([game(247, { live: live() })])),
    liveSourceSignal(slate([game(247, { live: live() }), game(248)])),
    liveSourceSignal(slate([game(247), game(248), game(249)])),
  ];

  assert.deepEqual(signals.map((x) => x.kind), ["no_games", "ok", "partial", "down"]);
  assert.equal(new Set(signals.map((x) => x.label)).size, 4, "四態文案不得共用");
  // 裁定 4 之後 ok 改符號，但**守的東西不變**：兩種「不需要做事」與兩種「要做事」
  // 在畫面上仍必須分得出來——前者一個是文字徽章一個是符號，後者兩句話不同且皆為警示色。
  const [noGames, ok, partial, down] = signals;
  assert.notEqual(noGames.display, ok.display);
  assert.notEqual(partial.label, down.label);
  for (const quiet of [noGames, ok]) {
    assert.notEqual(quiet.tone, "warn", "不需要行動的兩態不得用警示色");
  }
});

test("裁決B｜異常態要講得出幾場，維護者才知道規模", () => {
  const partial = liveSourceSignal(slate([game(247, { live: live() }), game(248), game(249)]));
  const down = liveSourceSignal(slate([game(247), game(248), game(249)]));

  // 「無」講的是不存在（開賽前本來就沒比賽在進行）；實際狀況是**取不到**（裁定 2）。
  assert.match(partial.label, /今日 3 場中 2 場無法取得即時賽況/);
  assert.match(down.label, /今日 3 場無法取得即時賽況/);
  for (const label of [partial.label, down.label]) {
    assert.equal(/無即時賽況/.test(label), false, "不得回到「無」的說法");
  }
});

test("**紅線**：訪客也看得到這一條，四態文案皆不得洩漏實作字彙", () => {
  const labels = [
    liveSourceSignal(null),
    liveSourceSignal(slate([game(247, { live: live() })])),
    liveSourceSignal(slate([game(247, { live: live() }), game(248)])),
    liveSourceSignal(slate([game(247), game(248), game(249)])),
    liveSourceSignal(slate([game(247)], { live_source: { status: "disabled", reason: null,
                                                         snapshots: 0, games: 1 } })),
  ].map((x) => x.label);

  for (const label of labels) {
    for (const word of ["Redis", "redis", "worker", "Worker", "當機", "掛掉", "錯誤", "URL", "API"]) {
      assert.equal(label.includes(word), false, `文案洩漏實作字彙 ${word}：${label}`);
    }
  }
});

test("未啟用即時來源（無 REDIS_URL 的本機／CI）與啟用卻拿不到，訪客面同一句", () => {
  // 兩者對維護者的意義不同，但那個差異由後端 `status` 判別碼承載；畫面上都是
  // 「今日 N 場皆無即時賽況」——訪客不需要、也不該讀到部署層的差別。
  const disabled = liveSourceSignal(slate([game(247)], {
    live_source: { status: "disabled", reason: null, snapshots: 0, games: 1 },
  }));

  assert.equal(disabled.kind, "down");
  assert.equal(disabled.label, liveSourceSignal(slate([game(247)])).label);
});

test("情境9｜final 當晚：官方事實取自 snapshot decisions，零模型衍生", () => {
  const done = live({
    phase: "final", freshness: "final", inning: 9,
    decisions: { winning_pitcher: { player_id: "A", name: "投手甲" }, losing_pitcher: null,
                 closer: null, mvp: { player_id: "B", name: "打者乙", yearly_count: 3 } },
  });
  const g = game(247, { live: done });
  assert.equal(todayCardKind(g), "final");
  assert.equal(officialFactLine(done), "單場 MVP 打者乙・勝投 投手甲");
  // DB 仍是 0–0（隔日爬蟲才補）——當晚看得到比分靠的就是 snapshot。
  assert.equal(g.completed, false);
  assert.equal(showTodaySlate(summaryOf(slate([g]))), true);
});

test("決勝全缺 → 官方紀錄確認中（不留空、不猜）；非 final 不給事實行", () => {
  assert.equal(officialFactLine(live({ phase: "final", decisions: null })),
               TODAY_COPY.officialPending);
  assert.equal(officialFactLine(live()), null);
  assert.equal(officialFactLine(null), null);
});

test("情境10｜跨日回退：今天的場次已入庫 → 仍是賽後態，且賽前機率不得回來", () => {
  const g = game(247, { completed: true, home_score: 6, away_score: 2, live: null });
  assert.equal(todayCardKind(g), "final");
  assert.equal(g.pregame, undefined, "後端不得對已開打場次送出 pregame 欄位");
  assert.equal(todayPollDelayMs(slate([g])), null, "都定案了就零 polling");
});

test("**紅線**：已開打場次一律不是賽前態（live／final／DB 已完成三條路徑）", () => {
  assert.equal(todayCardKind(game(1, { live: live() })), "live");
  assert.equal(todayCardKind(game(2, { live: live({ phase: "final" }) })), "final");
  assert.equal(todayCardKind(game(3, { completed: true })), "final");
});

test("裁定1｜延賽與保留賽是兩態，不可併成一個 suspended", () => {
  // GLOSSARY〈保留賽／delay_kind〉：官網 GameResult=1 是延賽（根本沒開打）、
  // =2 是保留（**已開賽後中止，場上有比分**）。併成一態就只能二選一地對其中一種說謊。
  assert.equal(todayCardKind(game(1, { live: live({ phase: "postponed" }) })), "postponed");
  assert.equal(todayCardKind(game(2, { live: live({ phase: "reserved" }) })), "reserved");
  // 兩者今天都不會再打完 → 皆為 settled，全場如此時零輪詢。
  assert.equal(todayPollDelayMs(slate([game(1, { live: live({ phase: "postponed" }) }),
                                       game(2, { live: live({ phase: "reserved" }) })])), null);
});

test("裁定1｜保留賽的比分不得被 DB 完成場判準吃成終場", () => {
  // 保留賽在 cpbl.games 裡帶著比分，而 `_serialize` 的完成場判準（有比分且日期不在未來）
  // 會把當天的保留賽算成 completed。若判定順序讓 `g.completed` 先講話，一場中止的比賽
  // 就會被畫成終場——所以 snapshot phase 必須優先於 DB 比分。
  const reserved = game(1, { completed: true, home_score: 2, away_score: 3,
                             live: live({ phase: "reserved", away_score: 3, home_score: 2 }) });

  assert.equal(todayCardKind(reserved), "reserved");
  // 對照：沒有 snapshot 時 DB 比分才當後備（隔日爬蟲補完的情形）。
  assert.equal(todayCardKind(game(2, { completed: true, live: null })), "final");
});

test("裁定1｜保留賽已開打，不得再掛賽前機率（後端不送 pregame 欄位）", () => {
  // 前端這一側只能證明「保留賽不是 pregame 態」；欄位缺席由後端釘住
  // （tests/test_daily_summary.py 的 LIVE_UNDERWAY_PHASES）。
  assert.notEqual(todayCardKind(game(1, { live: live({ phase: "reserved" }) })), "pregame");
});

test("排序 deterministic：開賽時間 → game_sno；無開賽時間者排在後面", () => {
  const games = [
    game(249, { live: live({ starts_at: "2026-08-07T18:35:00+08:00" }) }),
    game(247),
    game(248, { live: live({ starts_at: "2026-08-07T17:05:00+08:00" }) }),
    game(246, { live: live({ starts_at: "2026-08-07T18:35:00+08:00" }) }),
  ];
  assert.deepEqual(sortTodayGames(games).map((g) => g.game_sno), [248, 246, 249, 247]);
  // 純函式：不得就地改寫輸入。
  assert.deepEqual(games.map((g) => g.game_sno), [249, 247, 248, 246]);
});

test("**紅線**：today 有場次但都還沒開始時不得渲染今日賽事區塊（零空容器的另一面）", () => {
  assert.equal(showTodaySlate(summaryOf(slate([], { started: true }))), false);
  assert.equal(showTodaySlate(summaryOf(slate([game(247)], { started: false }))), false);
  assert.equal(showTodaySlate(summaryOf(slate([game(247, { live: live() })]))), true);
});

test("輪詢查詢字串由 SSR 那一份 response 的 scope 推導（結構上同源）", () => {
  assert.equal(dailySummaryQuery({ season: null, kind_code: "A", kinds: ["A"], as_of: "2026-08-07" }),
               "?kind_code=A");
  assert.equal(dailySummaryQuery({ season: 2026, kind_code: "D", kinds: ["D"], as_of: "2026-08-07" }),
               "?kind_code=D&season=2026");
});

test("**紅線**：本區塊不得出現任何 WP／WPA／leverage 欄位", () => {
  const keys = Object.keys(live());
  for (const banned of ["wp", "wpa", "leverage", "win_prob", "home_win_probability"]) {
    assert.equal(keys.some((k) => k.includes(banned)), false, `live view 不得帶 ${banned}`);
  }
});

test("phaseTone 走 StatusBadge 四語彙，不發明第五種狀態色", () => {
  assert.equal(phaseTone("live"), "live");
  assert.equal(phaseTone("final"), "done");
  assert.equal(phaseTone("postponed"), "warn");
  assert.equal(phaseTone("reserved"), "warn");
  assert.equal(phaseTone("unknown"), "warn");
  assert.equal(phaseTone("scheduled"), "scheduled");
  assert.equal(phaseTone("lineup_announced"), "scheduled");
});

// —— 最近比賽日的混合日（DAILY-MIXED-DAY-UX1，需求方 Design Gate 2026-08-16）——
//
// 場次資料全部照抄本機 DB 實查列，不自己編：混合日取 2026-08-09（A#253 完賽＋A#254／255
// 延賽）、無註記取 2025-09-24（D#143 完賽＋D#108 無註記且無取證）。
//
// ⚠️ 2023-08-01 的 A#175 **不能再當「未完成」的例子**：它是全庫 5 場經官方 box 取證的
// 0:0 真和局之一，後端改用 `is_completed_game` 之後回的是 `completed: true` ＋ 0:0 比分
// （Design Gate 第 8 項）。提案階段拿它當 fixture 是錯的，這一輪換掉。

const latestGame = (over: Partial<DailyGame> = {}): DailyGame => ({
  season: 2026, kind_code: "A", game_sno: 253, game_date: "2026-08-09", venue: "澄清湖",
  away_team_code: "B", away_team_name: "中信兄弟", away_score: 10,
  home_team_code: "T", home_team_name: "台鋼雄鷹", home_score: 2,
  completed: true, delay_kind: null, orig_date: null, ...over,
});

test("混合日：完賽場與延賽場分流，不把未完成場算成賽後卡", () => {
  // 2026-08-09 A 的三場，逐欄照抄 /api/v1/daily/summary 實測回應。
  const games = [
    latestGame(),
    latestGame({ game_sno: 254, away_team_name: "味全龍", home_team_name: "樂天桃猿",
                 away_score: null, home_score: null, completed: false,
                 delay_kind: "延賽", orig_date: "2026-08-09" }),
    latestGame({ game_sno: 255, away_team_name: "統一7-ELEVEn獅", home_team_name: "富邦悍將",
                 away_score: null, home_score: null, completed: false,
                 delay_kind: "延賽", orig_date: "2026-08-09" }),
  ];
  assert.deepEqual(games.map(latestGameStatus), ["final", "postponed", "postponed"]);
  assert.equal(latestDayPendingCount(games), 2);
});

test("全未完成日：計數不得假設至少一場完賽", () => {
  // 純函式的下界：`latestDayPendingCount` 不得靠「總場數 − 1」之類的假設。
  // 註：`latest_game_day` 取 `max(game_date) WHERE completed`，所以真實 API 回應裡這一天
  // **必然**至少有一場完賽；這裡測的是函式本身，不是宣稱那個日子存在。
  const games = [latestGame({ season: 2025, kind_code: "D", game_sno: 108,
                              game_date: "2025-09-24", venue: "斗六",
                              away_team_name: "富邦悍將二軍", home_team_name: "味全龍二軍",
                              away_score: null, home_score: null, completed: false })];
  assert.equal(latestDayPendingCount(games), 1);
  assert.equal(games.filter((g) => latestGameStatus(g) === "final").length, 0);
});

test("無註記情境：沒有 delay_kind 時走中性態，不得落到延賽或保留", () => {
  // 2025-09-24 D#108（0:0、無 delay_kind、無完賽取證）＋ 同日 D#143 完賽 10:3＝真實混合日。
  const g = latestGame({ season: 2025, kind_code: "D", game_sno: 108,
                         game_date: "2025-09-24", venue: "斗六",
                         away_team_name: "富邦悍將二軍", home_team_name: "味全龍二軍",
                         away_score: null, home_score: null, completed: false });
  assert.equal(latestGameStatus(g), "unrecorded");
  // 空字串與空白同樣是「沒有註記」——DB 實查確有空字串而非 NULL 的列。
  assert.equal(latestGameStatus({ ...g, delay_kind: "" }), "unrecorded");
  assert.equal(latestGameStatus({ ...g, delay_kind: "  " }), "unrecorded");
});

test("**取證的 0:0 真和局是賽果不是未完成**：後端送 completed 時走賽後卡", () => {
  // 2023-08-01 A#175：全庫 5 場經官方 box 取證的 0:0 和局之一。後端改判準後
  // （Design Gate 第 8 項）它帶 `completed: true` ＋ 0:0 比分抵達前端。
  const tie = latestGame({ season: 2023, game_sno: 175, game_date: "2023-08-01",
                           away_team_name: "味全龍", home_team_name: "統一7-ELEVEn獅",
                           away_score: 0, home_score: 0, completed: true });
  assert.equal(latestGameStatus(tie), "final");
  assert.equal(latestDayPendingCount([tie]), 0);
  // 賽後入口照給——和局也是賽果，不得因為 0:0 就退化成沒有連結的狀態卡。
  assert.equal(LATEST_FOOTER_COPY.final, "賽後復盤 →");
});

test("**紅線**：delay_kind 是歷史標記，已完成場不得被標成延賽", () => {
  // 2026-06-27 A#15：04-04 延到 06-27 後 2:9 打完，delay_kind 仍留著（全庫 41 場同型）。
  const played = latestGame({ game_sno: 15, game_date: "2026-06-27", away_score: 2, home_score: 9,
                              completed: true, delay_kind: "延賽", orig_date: "2026-04-04" });
  assert.equal(latestGameStatus(played), "final");
  assert.equal(latestDayPendingCount([played]), 0);
});

test("保留賽與延賽是兩態，文案不得共用", () => {
  const reserved = latestGame({ away_score: null, home_score: null, completed: false,
                                delay_kind: "保留", orig_date: "2026-06-14" });
  assert.equal(latestGameStatus(reserved), "reserved");
  assert.notEqual(LATEST_STATUS_COPY.reserved.label, LATEST_STATUS_COPY.postponed.label);
});

test("三句徽章文案＝需求方 Design Gate 裁定的字面，改動必須是刻意的", () => {
  // 這一條不是在測邏輯，是把裁定釘在版本控制裡：三句都是需求方逐條裁的，其中
  // 「保留比賽」還推翻過一版自創說法（「保留・擇期續賽」）。沒有這條，任何人都能
  // 順手把官方詞彙改回自撰註解而沒有任何東西轉紅。
  assert.equal(LATEST_STATUS_COPY.postponed.label, "延賽");
  assert.equal(LATEST_STATUS_COPY.reserved.label, "保留比賽");
  assert.equal(LATEST_STATUS_COPY.unrecorded.label, "無賽果紀錄");
  // 「無賽果紀錄」描述的是**我們的紀錄**，不宣稱有人正在確認——所以它的色調是中性的
  // scheduled 而不是要人行動的 warn；官方給了狀態的那兩態才是 warn。
  assert.equal(LATEST_STATUS_COPY.unrecorded.tone, "scheduled");
  assert.equal(LATEST_STATUS_COPY.postponed.tone, "warn");
  assert.equal(LATEST_STATUS_COPY.reserved.tone, "warn");
});

test("**紅線**：三句狀態文案都不得宣稱停賽原因或「未開打」", () => {
  const banned = ["雨", "颱", "天候", "未開打", "取消", "停電", "因"];
  for (const [key, { label }] of Object.entries(LATEST_STATUS_COPY)) {
    for (const word of banned) {
      assert.equal(label.includes(word), false, `${key} 文案不得出現未經證實的「${word}」`);
    }
  }
});

test("原定日期只在確實不同時才講；相同代表尚未排補賽日，不得無中生有", () => {
  const notRescheduled = latestGame({ game_sno: 254, completed: false, away_score: null,
                                      home_score: null, delay_kind: "延賽",
                                      orig_date: "2026-08-09" });
  assert.equal(latestGameDateNote(notRescheduled), null);
  const rescheduled = latestGame({ game_sno: 14, game_date: "2026-06-27", completed: false,
                                   away_score: null, home_score: null, delay_kind: "延賽",
                                   orig_date: "2026-04-04" });
  assert.equal(latestGameDateNote(rescheduled), "原定 04/04");
  // 已完成場不加註記——那是賽後卡，排程歷程不是它要講的事。
  assert.equal(latestGameDateNote(latestGame({ orig_date: "2026-04-04" })), null);
});

test("未完成場不給賽後入口：目前單場頁對延賽場是空的且標題寫 0：0", () => {
  // Design Gate 第 4 項：本卡不連結；title 缺陷（`entity-metadata.ts` 用 `score != null`
  // 而不是「打完了」）另開 UX-GAME-META-COMPLETED1（#148），本卡不修。
  assert.equal(LATEST_FOOTER_COPY.pending, null);
  assert.equal(LATEST_FOOTER_COPY.final, "賽後復盤 →");
});

// —— 今日賽事區塊的混合日（DAILY-MIXED-DAY-UX1 第二輪，需求方 Design Gate 2026-08-19）——
//
// 第一輪修的是「最近比賽日」那一塊（上一節）。2026-08-19 的真實混合日暴露出**今日賽事**
// 這一塊有同形的兩個缺陷，需求方當晚親眼看過本機畫面後裁定：
//   1. 延賽場次零標示——DB 已有 `delay_kind=延賽`，卡片一個字都沒用上，看起來像「還沒
//      開打、剛好沒有預測模型」；
//   2. freshness 條寫「今日 3 場無法取得即時賽況」，而同畫面兩張卡明白標著「比賽結束」
//      並顯示終局比分——假敘述，且就印在推翻它的證據旁邊。
//
// fixture 逐欄照抄當晚 `GET /api/v1/daily/summary`（本機 DB 於 22:57 刷新後）的實測回應：
//   A#273 台鋼雄鷹 8:6 統一獅  completed=true   live=null
//   A#274 樂天桃猿 vs 富邦悍將 completed=false  live=null  delay_kind=延賽  orig=2026-08-19
//   A#275 中信兄弟 6:2 味全龍  completed=true   live=null
//   live_source = { status: "disabled", snapshots: 0, games: 3 }
//
// ⚠️ 三場**都沒有 live snapshot**（本機沒開即時來源）。舊版 `todayCardKind` 只認
// `live.phase`，於是延賽場一路落到 `pregame`——這正是缺陷 1 的機制。

const aug19 = (over: Partial<TodayGame> = {}): TodayGame => ({
  season: 2026, kind_code: "A", game_sno: 273, game_date: "2026-08-19", venue: "澄清湖",
  away_team_code: "ADD011", away_team_name: "統一7-ELEVEn獅", away_score: 6,
  home_team_code: "AJL011", home_team_name: "台鋼雄鷹", home_score: 8,
  completed: true, delay_kind: null, orig_date: null, live: null, ...over,
} as TodayGame);

/** 當晚三場，順序照 API 回應。 */
const aug19Slate = (): TodaySlate => slate([
  aug19(),
  aug19({ game_sno: 274, away_team_name: "富邦悍將", home_team_name: "樂天桃猿",
          away_score: null, home_score: null, completed: false,
          delay_kind: "延賽", orig_date: "2026-08-19" }),
  aug19({ game_sno: 275, away_team_name: "中信兄弟", home_team_name: "味全龍",
          away_score: 6, home_score: 2 }),
], { game_date: "2026-08-19", started: true,
     live_source: { status: "disabled", reason: "即時來源未啟用", snapshots: 0, games: 3 } });

test("混合日｜今日賽事：延賽場靠官方 delay_kind 認出來，不再落到賽前態", () => {
  const s = aug19Slate();
  // 缺陷 1：舊版三場全是 ["final", "pregame", "final"]——延賽場與「還沒開打」同形。
  assert.deepEqual(s.games.map(todayCardKind), ["final", "postponed", "final"]);
  // 徽章文字只能是官方原文；`LATEST_STATUS_COPY` 與這裡是同一組詞彙。
  assert.equal(LATEST_STATUS_COPY.postponed.label, "延賽");
  // 三場都不會再變 → 完全停止輪詢（延賽場今天不會續打，見 `todayGameSettled`）。
  assert.equal(s.games.every(todayGameSettled), true);
  assert.equal(todayPollDelayMs(s), null);
});

test("無註記情境｜沒有 delay_kind 就不得生出狀態，空字串與空白也不算", () => {
  // 2025-09-24 D#108 那一類：日期已過、沒有比分、官方什麼都沒給。畫面上寧可是賽前態，
  // 也不得憑空生一個「延賽」——我們分不出它是沒打、打了沒爬到、還是官網沒更新。
  const bare = game(108, { game_date: "2025-09-24", kind_code: "D" });
  assert.equal(todayCardKind(bare), "pregame");
  assert.equal(todayCardKind({ ...bare, delay_kind: "" }), "pregame");
  assert.equal(todayCardKind({ ...bare, delay_kind: "   " }), "pregame");
  // 未知的第三種值同樣不得被當成狀態（值域實查只有「延賽」「保留」兩個）。
  assert.equal(todayCardKind({ ...bare, delay_kind: "改期" }), "pregame");
});

test("**紅線**：delay_kind 是歷史標記，補賽打完那天不得把終場誤標成延賽", () => {
  // 本機實查 41 場**已完成**場次帶著 delay_kind，例：2026-06-27 A#15 由 04-04 延來、
  // 最終 2:9 打完，`delay_kind` 仍是「延賽」。判定順序（completed 先）就是防這個。
  const madeUp = aug19({ game_sno: 15, game_date: "2026-06-27", orig_date: "2026-04-04",
                         away_score: 9, home_score: 2, completed: true, delay_kind: "延賽" });
  assert.equal(todayCardKind(madeUp), "final");
  // snapshot 仍然優先於 DB：worker 說在打，就是在打。
  assert.equal(todayCardKind({ ...madeUp, live: live({ phase: "live" }) }), "live");
});

test("保留賽：官方 GameResult=2 走自己那一態，不與延賽併桶", () => {
  const reserved = aug19({ game_sno: 164, completed: false, away_score: null, home_score: null,
                           delay_kind: "保留" });
  assert.equal(todayCardKind(reserved), "reserved");
  assert.equal(todayGameSettled(reserved), true);
  assert.notEqual(LATEST_STATUS_COPY.reserved.label, LATEST_STATUS_COPY.postponed.label);
});
