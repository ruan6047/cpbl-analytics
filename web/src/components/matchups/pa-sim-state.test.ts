import assert from "node:assert/strict";
import test from "node:test";

import {
  FIXTURE_ARTIFACT_ABSENT,
  FIXTURE_ARTIFACT_CORRUPT,
  FIXTURE_LEAGUE_FALLBACK_HITTER,
  FIXTURE_MISSING_OUTCOME,
  FIXTURE_OK_CLUTCH,
  FIXTURE_OK_NEUTRAL,
  FIXTURE_SUM_MISMATCH,
  FIXTURE_UNAVAILABLE_OTHER,
} from "./pa-sim-fixtures.ts";
import {
  ALL_OUTCOME_KEYS,
  DEFAULT_PA_STATE,
  OUT_KEYS,
  PA_OUTCOME_HINT,
  PA_OUTCOME_LABEL,
  PA_SIM_COPY,
  PA_SIM_DISCLOSURE,
  REACH_KEYS,
  SUM_TOLERANCE,
  basesLabel,
  batterSide,
  batterSideDelta,
  batterSideWinProbability,
  derivePaSimState,
  fmtDeltaPoints,
  fmtProbability,
  outcomeProbabilitySum,
  stateSummary,
} from "./pa-sim-state.ts";

// —— 驗收條件 3：四種退化各自獨立，且不產生替代機率 ——

test("四種退化態＋兩種 fail-closed 態各解出自己的 kind，不合併為泛用資料不足", () => {
  // unsupported：查詢賽事類型不在模擬母體內
  assert.equal(derivePaSimState("C", FIXTURE_OK_NEUTRAL, false).kind, "unsupported");
  assert.equal(derivePaSimState("E", FIXTURE_OK_NEUTRAL, false).kind, "unsupported");
  // artifact missing：未建置與損毀都歸 artifact 態（原因字串各自保留）
  assert.equal(derivePaSimState("A", FIXTURE_ARTIFACT_ABSENT, false).kind, "artifact_missing");
  assert.equal(derivePaSimState("A", FIXTURE_ARTIFACT_CORRUPT, false).kind, "artifact_missing");
  // unavailable：API 明示的其他原因
  assert.equal(derivePaSimState("A", FIXTURE_UNAVAILABLE_OTHER, false).kind, "unavailable");
  // api error：請求層失敗
  assert.equal(derivePaSimState("A", null, true).kind, "api_error");
  // 個人樣本缺失與契約破損
  assert.equal(
    derivePaSimState("A", FIXTURE_LEAGUE_FALLBACK_HITTER, false).kind,
    "league_fallback",
  );
  assert.equal(derivePaSimState("A", FIXTURE_SUM_MISMATCH, false).kind, "invariant_failed");
  assert.equal(derivePaSimState("A", FIXTURE_MISSING_OUTCOME, false).kind, "invariant_failed");
  // 正常態
  assert.equal(derivePaSimState("A", FIXTURE_OK_NEUTRAL, false).kind, "ok");
});

test("非 ok 態的狀態物件結構上不帶任何機率，呈現層沒有替代數字可用", () => {
  const states = [
    derivePaSimState("C", FIXTURE_OK_NEUTRAL, false),
    derivePaSimState("A", FIXTURE_ARTIFACT_ABSENT, false),
    derivePaSimState("A", FIXTURE_UNAVAILABLE_OTHER, false),
    derivePaSimState("A", null, true),
    derivePaSimState("A", FIXTURE_LEAGUE_FALLBACK_HITTER, false),
    derivePaSimState("A", FIXTURE_SUM_MISMATCH, false),
  ];
  for (const state of states) {
    assert.notEqual(state.kind, "ok");
    assert.ok(!("data" in state), `${state.kind} 不得攜帶 ok 資料`);
    assert.ok(!("outcomes" in state), `${state.kind} 不得攜帶結果分布`);
  }
});

test("賽事類型不符優先於一切：即使回應可用也不輸出機率", () => {
  // 若少了這道判定，C／E 會拿 A 母體的機率當成季後賽數字呈現。
  const state = derivePaSimState("C", FIXTURE_OK_CLUTCH, false);
  assert.equal(state.kind, "unsupported");
  if (state.kind === "unsupported") assert.equal(state.kindCode, "C");
});

test("賽別判定的優先序：C／E 不因回應內容改判成其他退化原因", () => {
  // 母體不符時本來就不該發出請求，故任何回應內容都必須維持 unsupported——
  // 若把賽別檢查排到 invariant／league 之後，使用者會看到錯誤的失敗原因。
  assert.equal(derivePaSimState("C", FIXTURE_SUM_MISMATCH, false).kind, "unsupported");
  assert.equal(derivePaSimState("E", FIXTURE_LEAGUE_FALLBACK_HITTER, false).kind, "unsupported");
  assert.equal(derivePaSimState("C", FIXTURE_ARTIFACT_ABSENT, false).kind, "unsupported");
  assert.equal(derivePaSimState("E", null, true).kind, "unsupported");
});

test("league fallback 依缺樣本的一側分流，不以聯盟平均補值", () => {
  const hitterSide = derivePaSimState("A", FIXTURE_LEAGUE_FALLBACK_HITTER, false);
  assert.equal(hitterSide.kind, "league_fallback");
  if (hitterSide.kind === "league_fallback") assert.equal(hitterSide.side, "hitter");

  const pitcherOnly = {
    ...FIXTURE_OK_NEUTRAL,
    sample: { ...FIXTURE_OK_NEUTRAL.sample, pitcher_pa: 0 },
  };
  const pitcherSide = derivePaSimState("A", pitcherOnly, false);
  assert.equal(pitcherSide.kind, "league_fallback");
  if (pitcherSide.kind === "league_fallback") assert.equal(pitcherSide.side, "pitcher");

  const bothMissing = {
    ...FIXTURE_OK_NEUTRAL,
    sample: { ...FIXTURE_OK_NEUTRAL.sample, hitter_pa: 0, pitcher_pa: 0 },
  };
  const both = derivePaSimState("A", bothMissing, false);
  assert.equal(both.kind, "league_fallback");
  if (both.kind === "league_fallback") assert.equal(both.side, "both");
});

// —— 驗收條件 2 之一：總和對帳（七種結果互斥且窮盡） ——

test("真實回應的七種結果機率總和為 1（容差內）", () => {
  for (const fixture of [FIXTURE_OK_NEUTRAL, FIXTURE_OK_CLUTCH]) {
    assert.ok(
      Math.abs(outcomeProbabilitySum(fixture) - 1) <= SUM_TOLERANCE,
      `總和 ${outcomeProbabilitySum(fixture)} 未過對帳`,
    );
  }
});

test("總和偏離容差即 fail-closed，並回報實際總和供留痕", () => {
  const state = derivePaSimState("A", FIXTURE_SUM_MISMATCH, false);
  assert.equal(state.kind, "invariant_failed");
  if (state.kind === "invariant_failed") {
    assert.ok(state.sum !== null && Math.abs(state.sum - 1) > SUM_TOLERANCE);
    assert.deepEqual(state.missing, []);
  }
});

test("結果集合缺鍵時回報缺哪一個，不對殘餘結果做局部顯示", () => {
  const state = derivePaSimState("A", FIXTURE_MISSING_OUTCOME, false);
  assert.equal(state.kind, "invariant_failed");
  if (state.kind === "invariant_failed") {
    assert.deepEqual(state.missing, ["HR"]);
    assert.equal(state.sum, null);
  }
});

test("結果鍵集合＝出局組＋上壘組，無重複無遺漏（顯示序固定）", () => {
  assert.equal(ALL_OUTCOME_KEYS.length, 7);
  assert.equal(new Set(ALL_OUTCOME_KEYS).size, 7);
  assert.deepEqual([...ALL_OUTCOME_KEYS], [...OUT_KEYS, ...REACH_KEYS]);
  for (const key of ALL_OUTCOME_KEYS) {
    assert.ok(PA_OUTCOME_LABEL[key], `${key} 缺中文標籤`);
    assert.ok(PA_OUTCOME_HINT[key], `${key} 缺白話說明`);
  }
  // 每個結果鍵都存在於真實回應中（契約對帳，非想像欄位）
  for (const key of ALL_OUTCOME_KEYS) {
    assert.ok(FIXTURE_OK_NEUTRAL.outcomes[key], `真實回應缺 ${key}`);
  }
});

// —— 驗收條件 2 之二：文案紅線 ——

const ALL_COPY = [
  ...Object.values(PA_SIM_COPY).flatMap((entry) => [entry.title, entry.body]),
  ...Object.values(PA_SIM_DISCLOSURE),
];

test("六種非 ok 態的標題與說明彼此互異（不共用文案）", () => {
  const entries = Object.values(PA_SIM_COPY);
  assert.equal(entries.length, 6);
  assert.equal(new Set(entries.map((entry) => entry.title)).size, 6);
  assert.equal(new Set(entries.map((entry) => entry.body)).size, 6);
});

test("模型資產問題與這組對決缺資料的文案不得混同", () => {
  // artifact 是模型資產狀態；league_fallback 才是這組球員的樣本問題。
  assert.ok(PA_SIM_COPY.artifact_missing.body.includes("不是這組對決缺資料"));
  assert.ok(!PA_SIM_COPY.artifact_missing.title.includes("樣本"));
  assert.ok(PA_SIM_COPY.league_fallback.body.includes("聯盟"));
  assert.ok(!PA_SIM_COPY.api_error.title.includes("樣本"));
});

test("『信賴區間』只允許出現在否定語境（ml-sim1-review 殘餘風險 3）", () => {
  for (const text of ALL_COPY) {
    if (!text.includes("信賴區間")) continue;
    assert.match(
      text,
      /(不是|非|不得)[^。]{0,8}信賴區間/,
      `文案把區間稱為信賴區間：${text}`,
    );
  }
  // 且必須有一處明確否定，不能整組文案都不提方法性質
  assert.match(PA_SIM_DISCLOSURE.intervalNote, /不是統計信賴區間/);
});

test("不得宣稱整場勝負預測提升；weighted 只能以等效＋不用於預測陳述", () => {
  for (const text of ALL_COPY) {
    assert.doesNotMatch(
      text,
      /(提升|更準|勝過|優於)[^。]{0,10}(整場|比賽|勝負|勝率預測)/,
      `文案宣稱整場預測提升：${text}`,
    );
    assert.ok(!text.includes("必勝"), `文案出現必勝：${text}`);
    assert.ok(!text.includes("保證"), `文案出現保證：${text}`);
    assert.ok(!text.includes("天敵"), `文案出現天敵：${text}`);
  }
  assert.ok(PA_SIM_DISCLOSURE.weightedNote.includes("等效"));
  assert.match(PA_SIM_DISCLOSURE.weightedNote, /不用來預測/);
  assert.match(PA_SIM_DISCLOSURE.scopeNote, /不預測整場勝負/);
});

test("『剋』字只允許出現在否定語境（禁確定性天敵語氣）", () => {
  for (const text of ALL_COPY) {
    if (!text.includes("剋")) continue;
    assert.match(text, /不(代表|是|意味)[^。]{0,8}剋/, `文案帶確定性相剋語氣：${text}`);
  }
});

test("情境揭露必須說明機率與情境的關係，避免誤讀為情境改變機率", () => {
  assert.match(PA_SIM_DISCLOSURE.situationNote, /不改變結果機率/);
  assert.match(PA_SIM_DISCLOSURE.shrinkageNote, /直接對戰/);
});

// —— 視角與格式（呈現層純函式） ——

test("delta 號向依 half 翻轉為打者方視角，量值不變", () => {
  const clutchHr = FIXTURE_OK_CLUTCH.outcomes.HR.delta_wp;
  // 9 局下（half=2）打者屬主隊：主隊視角與打者方視角同號
  assert.equal(batterSide("2"), "home");
  assert.equal(batterSideDelta("2", clutchHr), clutchHr);
  assert.ok(batterSideDelta("2", clutchHr) > 0, "滿壘落後開轟對打者方必為正向");

  const neutralHr = FIXTURE_OK_NEUTRAL.outcomes.HR.delta_wp;
  // 1 局上（half=1）打者屬客隊：主隊 delta 為負，打者方應翻為正
  assert.equal(batterSide("1"), "away");
  assert.ok(neutralHr < 0, "客隊開轟會壓低主隊勝率");
  assert.equal(batterSideDelta("1", neutralHr), -neutralHr);
  assert.ok(batterSideDelta("1", neutralHr) > 0);
  // 只翻號向不改量值
  assert.equal(Math.abs(batterSideDelta("1", neutralHr)), Math.abs(neutralHr));
});

test("勝率視角換算為零和（客隊＝1 − 主隊），不重新估計", () => {
  const home = FIXTURE_OK_CLUTCH.current_win_probability;
  assert.equal(batterSideWinProbability("2", home), home);
  assert.equal(batterSideWinProbability("1", home), 1 - home);
  // 兩視角相加恆為 1（任何 half 都成立）
  for (const half of ["1", "2"] as const) {
    const batter = batterSideWinProbability(half, home);
    const other = batterSideWinProbability(half === "1" ? "2" : "1", home);
    assert.ok(Math.abs(batter + other - 1) < 1e-12);
  }
});

test("三振對打者方一律不利，兩種 half 皆成立", () => {
  assert.ok(batterSideDelta("2", FIXTURE_OK_CLUTCH.outcomes.K.delta_wp) < 0);
  assert.ok(batterSideDelta("1", FIXTURE_OK_NEUTRAL.outcomes.K.delta_wp) < 0);
});

test("預設情境為中性起始狀態，不預設高槓桿戲劇情境", () => {
  assert.deepEqual(DEFAULT_PA_STATE, {
    inning: 1,
    half: "1",
    bases: "___",
    outs: 0,
    away_score: 0,
    home_score: 0,
  });
});

test("壘況與情境摘要可讀，且摘要涵蓋全部五個輸入軸", () => {
  assert.equal(basesLabel("___"), "壘上無人");
  assert.equal(basesLabel("123"), "滿壘");
  assert.equal(basesLabel("1_3"), "一三壘有人");
  const summary = stateSummary(FIXTURE_OK_CLUTCH.state);
  for (const part of ["9 局下半", "2 出局", "滿壘", "客 3", "主 2"]) {
    assert.ok(summary.includes(part), `摘要缺 ${part}：${summary}`);
  }
});

test("數值格式：機率百分比一位小數、delta 百分點帶正負號", () => {
  assert.equal(fmtProbability(0.12926217076869428), "12.9%");
  assert.equal(fmtProbability(1), "100.0%");
  assert.equal(fmtDeltaPoints(0.6372), "+63.7");
  assert.equal(fmtDeltaPoints(-0.2858), "−28.6");
  assert.equal(fmtDeltaPoints(0), "+0.0");
});
