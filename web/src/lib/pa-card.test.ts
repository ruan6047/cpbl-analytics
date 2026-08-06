import assert from "node:assert/strict";
import test from "node:test";

import { basesFromEvent, buildPaCardVM, marginTextOf, paCardLabel, paScoreLineOf } from "./pa-card.ts";
import type { PaFact } from "./game-facts.ts";

const fact = (over: Partial<PaFact> = {}): PaFact => ({
  pa_id: "pa-1", pa_index: 1, state: "ready", inning: 7, half: "2",
  outs_before: 2, bases_before: ["1", "3"],
  away_score_before: 4, home_score_before: 2, away_score_after: 4, home_score_after: 4,
  hitter: { player_id: "H1", name: "陳文杰" },
  end_hitter: { player_id: "H1", name: "陳文杰" },
  pitcher: { player_id: "P1", name: "蘇俊璋" },
  result_action: "一壘安打", outcome_family: "hit",
  start_event_no: "580", end_event_no: "585", member_event_nos: ["580", "585"],
  runs_on_play: 2, delta_re24: 1.61, unavailable_reason: null, garbage_time: false,
  ...over,
});

const ev = (over: Record<string, unknown> = {}) => ({
  inning_seq: 7, visiting_home_type: "2", out_cnt: 2,
  first_base: "王一", second_base: null, third_base: "李三",
  action_name: "一壘安打", main_event_no: "580", ...over,
});

test("canonical 打席優先：局面與比分全取事實流", () => {
  const vm = buildPaCardVM(fact(), ev({ out_cnt: 99, first_base: null, third_base: null }),
    ev(), { runs: 0, away: 9, home: 9 }, null, 0);
  assert.equal(vm.outsBefore, 2);                    // 不吃 livelog 的 99
  assert.deepEqual(vm.basesBefore, ["1", "3"]);      // 不吃 livelog 的空壘
  assert.equal(vm.margin, "4–2");                    // 不吃 preScore 的 9-9
  assert.deepEqual(vm.scoreAfter, { away: 4, home: 4 });
  assert.equal(vm.runs, 2);
  assert.equal(vm.deltaRe24, 1.61);
});

test("事實流缺席：退回 livelog 首事件的打席前狀態", () => {
  const vm = buildPaCardVM(null, ev(), ev(), { runs: 0, away: 4, home: 2 },
    { away: 4, home: 4 }, 2);
  assert.equal(vm.inning, 7);
  assert.equal(vm.half, "2");
  assert.equal(vm.outsBefore, 2);                    // out_cnt 是打席前出局數
  assert.deepEqual(vm.basesBefore, ["1", "3"]);
  assert.equal(vm.margin, "4–2");                    // 首事件**之前**的累計比分
  assert.deepEqual(vm.scoreAfter, { away: 4, home: 4 });
  assert.equal(vm.runs, 2);
  assert.equal(vm.deltaRe24, null);                  // 退路不自行推算 ΔRE24
});

test("非 ready 的 canonical 打席（截斷／突破僵局佈局列）也走退路，不顯示 ΔRE24", () => {
  const vm = buildPaCardVM(fact({ state: "truncated", delta_re24: null }), ev(), ev(),
    { runs: 0, away: 1, home: 0 }, null, 0);
  assert.equal(vm.deltaRe24, null);
  assert.equal(vm.margin, "1–0");                    // 用 livelog 退路而非事實流的比分
});

test("官方結果：事實流優先，缺值退回末事件的 action_name", () => {
  assert.equal(buildPaCardVM(fact(), ev(), ev(), null, null, 0).resultAction, "一壘安打");
  assert.equal(buildPaCardVM(null, ev(), ev({ action_name: "  三振出局 " }), null, null, 0)
    .resultAction, "三振出局");
  assert.equal(buildPaCardVM(null, ev(), ev({ action_name: "" }), null, null, 0)
    .resultAction, null);
});

test("首事件之前沒有累計比分（半局首打席在全場第一列）時不編比分", () => {
  const vm = buildPaCardVM(null, ev(), ev(), null, null, 0);
  assert.equal(vm.margin, "");
});

test("marginTextOf：大者在前；平手也出數字（不寫「平手」）；缺值回空字串", () => {
  assert.equal(marginTextOf(2, 6), "6–2");
  // 「平手」把 0–0 與 7–7 壓成同一個詞，資訊被丟掉；數字相等本身已自明
  assert.equal(marginTextOf(3, 3), "3–3");
  assert.equal(marginTextOf(0, 0), "0–0");
  assert.equal(marginTextOf(null, 1), "");
});

test("basesFromEvent：只認有人的壘位，順序固定一二三", () => {
  assert.deepEqual(basesFromEvent(ev({ second_base: "張二" })), ["1", "2", "3"]);
  assert.deepEqual(basesFromEvent(ev({ first_base: null, third_base: null })), []);
  assert.deepEqual(basesFromEvent(undefined), []);
});

test("paScoreLineOf：進帳掛在進攻方那一側（上半局客隊、下半局主隊）", () => {
  assert.deepEqual(paScoreLineOf({ scoreAfter: { away: 2, home: 4 }, runs: 2, half: "2" }),
    { away: 2, home: 4, runs: 2, side: "home" });
  assert.deepEqual(paScoreLineOf({ scoreAfter: { away: 3, home: 1 }, runs: 1, half: "1" }),
    { away: 3, home: 1, runs: 1, side: "away" });
});

test("paScoreLineOf：非得分打席／比分缺值不出比分列", () => {
  assert.equal(paScoreLineOf({ scoreAfter: { away: 2, home: 4 }, runs: 0, half: "2" }), null);
  assert.equal(paScoreLineOf({ scoreAfter: { away: 2, home: 4 }, runs: null, half: "2" }), null);
  assert.equal(paScoreLineOf({ scoreAfter: null, runs: 2, half: "2" }), null);
});

test("paScoreLineOf：半局不明時不亂掛一側（side 為 null）", () => {
  assert.equal(paScoreLineOf({ scoreAfter: { away: 2, home: 4 }, runs: 2, half: null })?.side, null);
});

test("paScoreLineOf：比分一律取 score_after，不由前值＋進帳推算", () => {
  // 一個打席多次得分時，前值＋進帳的舊算法會漏掉中間的變化；此處釘住只吃 scoreAfter。
  const vm = buildPaCardVM(fact({ away_score_before: 0, home_score_before: 0, runs_on_play: 3,
    away_score_after: 0, home_score_after: 3 }), ev(), ev(), null, null, 0);
  assert.deepEqual(paScoreLineOf(vm), { away: 0, home: 3, runs: 3, side: "home" });
});

test("paCardLabel：壘包圖示要有文字替代（a11y）", () => {
  const vm = buildPaCardVM(fact(), ev(), ev(), null, null, 0);
  assert.match(paCardLabel(vm, "陳文杰", "，勝率推向台鋼雄鷹 29 個百分點"),
    /7 局下.*2 出局.*一、三壘有人.*陳文杰 一壘安打.*台鋼雄鷹 29 個百分點/);
  const empty = buildPaCardVM(fact({ bases_before: [] }), ev(), ev(), null, null, 0);
  assert.match(paCardLabel(empty, "打者", ""), /壘上無人/);
  const loaded = buildPaCardVM(fact({ bases_before: ["1", "2", "3"] }), ev(), ev(), null, null, 0);
  assert.match(paCardLabel(loaded, "打者", ""), /滿壘/);
});
