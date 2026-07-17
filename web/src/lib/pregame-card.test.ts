import assert from "node:assert/strict";
import test from "node:test";

import { PREGAME_FIXTURES } from "./pregame-card-fixtures.ts";
import {
  PREGAME_COPY,
  formatProbability,
  pickPrimarySignal,
  resolvePregameCard,
} from "./pregame-card.ts";

// —— 五態狀態機（驗收條件 2）——

test("五個 fixture 各解出對應狀態，缺模型不阻塞也不擲錯", () => {
  assert.equal(resolvePregameCard(PREGAME_FIXTURES.available).status, "available");
  assert.equal(
    resolvePregameCard(PREGAME_FIXTURES.artifact_missing).status,
    "missing_artifact"
  );
  assert.equal(resolvePregameCard(PREGAME_FIXTURES.unsupported).status, "unsupported");
  assert.equal(resolvePregameCard(PREGAME_FIXTURES.pending).status, "pending");
  assert.equal(resolvePregameCard(PREGAME_FIXTURES.error).status, "error");
});

test("不可用三態＋error 均不含機率欄位——嚴禁補 50% 假數字", () => {
  for (const name of ["artifact_missing", "unsupported", "pending", "error"] as const) {
    const model = resolvePregameCard(PREGAME_FIXTURES[name]);
    assert.equal("homeWinProbability" in model, false, `${name} 不得帶機率`);
    assert.equal("probabilityText" in model, false, `${name} 不得帶機率文字`);
    assert.equal(
      JSON.stringify(model).includes("50%"),
      false,
      `${name} 文案不得出現 50%`
    );
    assert.ok(("message" in model && model.message.length > 0), `${name} 需給說明文案`);
  }
});

test("unsupported 判定看賽別而非 response：二軍場即使 API 有資料也不渲染機率", () => {
  const model = resolvePregameCard(PREGAME_FIXTURES.unsupported);
  assert.equal(model.status, "unsupported");
});

// —— 點機率＋1 個主要訊號（驗收條件 1）——

test("available 只有一個點機率，view model 不含任何區間欄位", () => {
  const model = resolvePregameCard(PREGAME_FIXTURES.available);
  assert.equal(model.status, "available");
  assert.ok(model.status === "available");
  assert.equal(model.probabilityText, "62%");
  // API payload 帶 model_interval_90，但 view model 任何 key/值都不得夾帶區間。
  const dump = JSON.stringify(model).toLowerCase();
  assert.equal(/interval/.test(dump), false, "view model 不得含 interval 欄位");
  assert.equal(dump.includes("0.541"), false, "區間端點值不得洩入 view model");
  assert.equal(dump.includes("0.688"), false, "區間端點值不得洩入 view model");
});

test("主訊號採固定群優先序：suppression 有值時優先", () => {
  const model = resolvePregameCard(PREGAME_FIXTURES.available);
  assert.ok(model.status === "available");
  assert.equal(model.primarySignal?.key, "starter_era_diff");
  assert.equal(model.primarySignal?.label, "先發投手ERA差");
  assert.equal(model.primarySignal?.valueText, "-0.84");
  // starter_era_diff 是 lower_favors_home：主隊先發 ERA 低 0.84 → 利主隊。
  assert.equal(model.primarySignal?.favors, "home");
  assert.equal(model.primarySignal?.favorsText, PREGAME_COPY.favorsHome);
});

test("suppression 缺值（先發未公布）時主訊號退位到 strength", () => {
  const model = resolvePregameCard(PREGAME_FIXTURES.available_no_starter);
  assert.ok(model.status === "available");
  assert.equal(model.primarySignal?.key, "winrate_diff");
  assert.equal(model.primarySignal?.valueText, "+0.058");
  assert.equal(model.primarySignal?.favors, "home");
});

test("訊號全缺值時 primarySignal 為 null，仍保留點機率、不造假訊號", () => {
  const signal = pickPrimarySignal({
    strength: { key: "winrate_diff", raw: null, direction: "higher_favors_home" },
    suppression: { key: "starter_era_diff", raw: null, direction: "lower_favors_home" },
  });
  assert.equal(signal, null);
});

test("raw=0 判為兩隊持平；higher_favors_home 負值判利客隊", () => {
  const even = pickPrimarySignal({
    schedule: { key: "rest_days_diff", raw: 0, direction: "higher_favors_home" },
  });
  assert.equal(even?.favors, "even");
  assert.equal(even?.favorsText, PREGAME_COPY.favorsEven);
  const away = pickPrimarySignal({
    strength: { key: "winrate_diff", raw: -0.1, direction: "higher_favors_home" },
  });
  assert.equal(away?.favors, "away");
});

// —— 機率顯示（整數 %，不給假精度，極端值不顯示 100%/0%）——

test("點機率顯示為整數百分比，極端值退為 >99% / <1%", () => {
  assert.equal(formatProbability(0.617), "62%");
  assert.equal(formatProbability(0.5), "50%");
  assert.equal(formatProbability(0.999), ">99%");
  assert.equal(formatProbability(0.001), "<1%");
});

// —— 文案紅線（驗收條件 1／3）——

test("卡片文案表整體不得出現「信賴區間」與任何區間敘述", () => {
  const copy = JSON.stringify(PREGAME_COPY);
  assert.equal(copy.includes("信賴區間"), false);
  assert.equal(copy.includes("區間"), false, "區間敘述只屬賽事頁／方法頁");
});

test("方法頁連結固定指向 /methodology#pregame（anchor 契約單一來源）", () => {
  for (const fixture of Object.values(PREGAME_FIXTURES)) {
    const model = resolvePregameCard(fixture);
    assert.equal(model.methodologyHref, "/methodology#pregame");
  }
});

test("模型 freshness 附註存在且語意為「模型資料至 N 季」", () => {
  const model = resolvePregameCard(PREGAME_FIXTURES.available);
  assert.ok(model.status === "available");
  assert.equal(model.trainedThroughText, "模型資料至 2025 季");
});
