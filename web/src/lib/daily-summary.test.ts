import assert from "node:assert/strict";
import test from "node:test";

import {
  resolvePregameFromDaily,
  pregameServingNotice,
  homePregameNotice,
  refreshCopy,
  refreshAgeText,
  shortDate,
  slateDistanceText,
  gameHref,
  REFRESH_COPY,
  type DailyGamePregame,
  type DailySummary,
  type RefreshStatus,
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

test("refreshAgeText 依時距分桶；null → null", () => {
  assert.equal(refreshAgeText(null), null);
  assert.equal(refreshAgeText(0.4), "1 小時內");
  assert.equal(refreshAgeText(5), "5 小時前");
  assert.equal(refreshAgeText(50), "2 天前");
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
