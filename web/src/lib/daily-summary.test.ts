import assert from "node:assert/strict";
import test from "node:test";

import {
  resolvePregameFromDaily,
  refreshCopy,
  refreshAgeText,
  shortDate,
  slateDistanceText,
  gameHref,
  REFRESH_COPY,
  type DailyGamePregame,
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
