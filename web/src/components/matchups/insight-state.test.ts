import assert from "node:assert/strict";
import test from "node:test";

import {
  FIXTURE_GATED,
  FIXTURE_LOW_COVERAGE,
  FIXTURE_NO_BASELINE_CE,
  FIXTURE_NO_PRIOR,
  FIXTURE_OK_BATTING,
  FIXTURE_OK_PITCHING_FLIPPED,
} from "./insight-fixtures.ts";
import {
  INSIGHT_COPY,
  INSIGHT_LABELS,
  deriveInsightState,
  fmtDelta,
  subjectDelta,
} from "./insight-state.ts";

// —— 四種 fail-closed 狀態各自獨立（驗收條件 2）——

test("四種 fail-closed fixture 各解出對應狀態，不合併為泛用資料不足", () => {
  assert.equal(deriveInsightState(FIXTURE_LOW_COVERAGE).kind, "low_coverage");
  assert.equal(deriveInsightState(FIXTURE_NO_PRIOR).kind, "no_prior");
  assert.equal(deriveInsightState(FIXTURE_GATED).kind, "gated");
  assert.equal(deriveInsightState(FIXTURE_NO_BASELINE_CE).kind, "no_baseline");
});

test("四種 fail-closed 文案標題彼此相異，且說明不共用", () => {
  const entries = [
    INSIGHT_COPY.low_coverage,
    INSIGHT_COPY.no_prior,
    INSIGHT_COPY.gated,
    INSIGHT_COPY.no_baseline,
  ];
  assert.equal(new Set(entries.map((e) => e.title)).size, 4);
  assert.equal(new Set(entries.map((e) => e.body)).size, 4);
});

test("低覆蓋狀態帶回 API 的覆蓋率與閘門值（不自創閾值）", () => {
  const s = deriveInsightState(FIXTURE_LOW_COVERAGE);
  assert.equal(s.kind, "low_coverage");
  if (s.kind === "low_coverage") {
    assert.equal(s.ratio, FIXTURE_LOW_COVERAGE.coverage?.ratio);
    assert.equal(s.gate, FIXTURE_LOW_COVERAGE.coverage?.gate);
  }
});

test("C–E 契約：baseline／league／coverage 皆 null 時仍為 no_baseline 而非崩潰", () => {
  assert.equal(FIXTURE_NO_BASELINE_CE.baseline, null);
  assert.equal(FIXTURE_NO_BASELINE_CE.league, null);
  assert.equal(FIXTURE_NO_BASELINE_CE.coverage, null);
  const s = deriveInsightState(FIXTURE_NO_BASELINE_CE);
  assert.equal(s.kind, "no_baseline");
  if (s.kind === "no_baseline") assert.match(s.note, /baseline/);
});

test("kind A 但 coverage null（無母體／無對戰）走 no_data，不誤標為 C–E", () => {
  const s = deriveInsightState({
    ...FIXTURE_NO_BASELINE_CE,
    kind_code: "A",
    sample_note: "該球員在此範圍沒有對戰紀錄",
  });
  assert.equal(s.kind, "no_data");
});

// —— 低樣本／credibility 閘門（驗收條件 1）——

test("低樣本：候選全被 credibility 閘門擋下時為 gated，帶 eligible/gated_out", () => {
  const s = deriveInsightState(FIXTURE_GATED);
  assert.equal(s.kind, "gated");
  if (s.kind === "gated") {
    assert.equal(s.eligible, 0);
    assert.equal(s.gatedOut, 41);
  }
});

test("通過全部閘門才是 ok，且候選確實存在", () => {
  const s = deriveInsightState(FIXTURE_OK_BATTING);
  assert.equal(s.kind, "ok");
  assert.ok(FIXTURE_OK_BATTING.advantages.length > 0);
  assert.ok(FIXTURE_OK_BATTING.disadvantages.length > 0);
});

test("判定順序：覆蓋率閘門優先於先驗；先驗優先於 credibility", () => {
  // 覆蓋率沒過時，即使 prior_available=false 也應報 low_coverage（API 該情境不會算先驗）
  const s1 = deriveInsightState({
    ...FIXTURE_LOW_COVERAGE,
    method: { ...FIXTURE_LOW_COVERAGE.method, prior_available: false },
  });
  assert.equal(s1.kind, "low_coverage");
  // 先驗缺席時即使候選為空也應報 no_prior 而非 gated
  assert.equal(deriveInsightState(FIXTURE_NO_PRIOR).kind, "no_prior");
});

// —— 禁止確定語氣（驗收條件 1：禁「天敵」斷言）——

test("洞察標籤用候選語氣，全部文案不出現「天敵」斷言", () => {
  assert.match(INSIGHT_LABELS.disadvantages, /候選/);
  assert.match(INSIGHT_LABELS.advantages, /候選/);
  const all = [
    ...Object.values(INSIGHT_COPY).flatMap((c) => [c.title, c.body]),
    ...Object.values(INSIGHT_LABELS),
  ].join("");
  assert.ok(!all.includes("天敵"));
  assert.ok(!all.includes("輕微優勢")); // gated 不可改稱輕微優勢（藍圖 §5.9）
});

// —— 角色翻轉（對稱性呈現；統計對稱由 API 建構保證）——

test("角色翻轉：同組對戰 delta 主角視角號向鏡像、|delta| 不變", () => {
  const battingSide = FIXTURE_OK_BATTING.disadvantages[0]; // 林泓育視角：劣勢
  const pitchingSide = FIXTURE_OK_PITCHING_FLIPPED.advantages[0]; // 陳鴻文視角：優勢
  // API 契約：同組對戰 delta_shrunk 同值（號向固定＝正有利打者）
  assert.equal(battingSide.delta_shrunk, pitchingSide.delta_shrunk);
  const b = subjectDelta("batting", battingSide.delta_shrunk);
  const p = subjectDelta("pitching", pitchingSide.delta_shrunk);
  assert.ok(b < 0); // 打者主角：劣勢＝負
  assert.ok(p > 0); // 投手主角：同組對戰＝優勢＝正
  assert.equal(Math.abs(b), Math.abs(p));
});

test("角色翻轉：優勢／劣勢清單鏡像（打者的劣勢＝該投手的優勢）", () => {
  const battingDisIds = FIXTURE_OK_BATTING.disadvantages.map((c) => c.opp_id);
  const pitchingAdvIds = FIXTURE_OK_PITCHING_FLIPPED.advantages.map((c) => c.opp_id);
  assert.ok(battingDisIds.includes(FIXTURE_OK_PITCHING_FLIPPED.player_id));
  assert.ok(pitchingAdvIds.includes(FIXTURE_OK_BATTING.player_id));
});

test("fmtDelta 依主角視角帶正負號", () => {
  assert.equal(fmtDelta("batting", 0.0278), "+0.028");
  assert.equal(fmtDelta("batting", -0.0298), "−0.030");
  assert.equal(fmtDelta("pitching", -0.0298), "+0.030");
});

// —— coverage 與 sample_scope 不混淆（驗收條件 3）——

test("insights coverage 是全 scope 評估，與 query_sample 分開", () => {
  assert.equal(FIXTURE_OK_BATTING.coverage?.scope, "all_opponents");
  // 隊伍篩選只縮 query_sample，不影響 coverage 語意：兩者鍵名/結構不同
  assert.ok("ratio" in (FIXTURE_OK_BATTING.coverage ?? {}));
  assert.ok("opponents" in FIXTURE_OK_BATTING.query_sample);
  assert.ok(!("ratio" in FIXTURE_OK_BATTING.query_sample));
});
