import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildHighlights, errorEvents, type HighlightInput } from "./game-highlights.ts";

// #285 批次 F：失誤事件表與五個新標籤（道歉全壘打／道歉野球／一棒逆轉／一棒追平／致命失誤，因果版 F-Q1、F-Q3）。
// 夾具＝2026 季後六場真實投影（含 errors／catcher_acnt／defend_station_code），見 _provenance；反例由真實列複製後改單一欄位。

const FX = JSON.parse(readFileSync(new URL("./__fixtures__/game-highlights_2026-batchF.json", import.meta.url), "utf8")) as {
  input: Record<string, HighlightInput>;
};
const NEW = /道歉全壘打$|道歉野球$|一棒逆轉$|一棒追平$|致命失誤（\d+ 局）$/;
const news = (inp: HighlightInput, completed = true) => buildHighlights(inp, completed).filter((h) => NEW.test(h.text));
const clone = (k: string) => structuredClone(FX.input[k]);

test("2026 季後六場黃金值（因果版）：只有 C2 三個、E4 一個", () => {
  assert.deepEqual(news(FX.input.C2), [
    { text: "曾聖安 道歉全壘打", team: "AAA011" },
    { text: "曾聖安 一棒逆轉", team: "AAA011" },
    { text: "兄弟 致命失誤（5 局）", team: "ACN011" },
  ]);
  assert.deepEqual(news(FX.input.E4), [{ text: "陳聖平 道歉野球", team: "ADD011" }]);
  for (const k of ["E1", "E2", "E3", "C1"]) assert.deepEqual(news(FX.input[k]), [], k);
});

test("失誤事件表：C2 四次具名失誤全部對帳通過、唯一歸屬；受影響跑者含打者上壘與跑者進壘", () => {
  const { events, halfOk } = errorEvents(FX.input.C2);
  assert.ok([...halfOk.values()].every(Boolean));
  assert.ok(events.length > 0 && events.every((e) => e.playerAcnt !== null && e.affected !== null));
  const five = events.filter((e) => e.inning === 5);
  assert.deepEqual(five.map((e) => [e.fieldingSide, e.position, [...e.affected!]]), [
    ["2", "RF", ["宋晟睿"]],          // 一壘跑者宋晟睿 因右外野手 失誤上二壘
    ["1", "1B", ["陳子豪"]],          // 打者陳子豪 一壘手 接球失誤上一壘
  ]);
});

test("因果版：C2 5 局上味全守備（失誤跑者宋晟睿沒有得分）不標；5 局下兄弟守備（陳子豪隨三分砲得分）標", () => {
  const t = news(FX.input.C2).map((h) => h.text);
  assert.ok(t.includes("兄弟 致命失誤（5 局）"));
  assert.ok(!t.some((x) => x.startsWith("味全 致命失誤")));
});

test("F-Q3：失誤者打出全壘打（也有打點）只出道歉全壘打，不再出道歉野球", () => {
  const t = news(FX.input.C2).map((h) => h.text);
  assert.ok(t.includes("曾聖安 道歉全壘打") && !t.includes("曾聖安 道歉野球"));
});

test("半局對帳不過 ⇒ 該半局失誤時點與歸屬不明：道歉／致命都不標", () => {
  const inp = clone("C2");
  for (const r of inp.scoreboard) if (Number(r.error_cnt) > 0) r.error_cnt = Number(r.error_cnt) + 1;
  const t = news(inp).map((h) => h.text);
  assert.ok(!t.some((x) => /道歉|致命/.test(x)), t.join("/"));
  assert.ok(t.includes("曾聖安 一棒逆轉"));                       // 與失誤無關的規則照常
  assert.ok(errorEvents(inp).events.every((e) => e.playerAcnt === null));
});

test("缺欄位（舊夾具沒有 errors／catcher_acnt／defend_station_code）不擲錯、不歸屬", () => {
  const inp = clone("E4");
  for (const r of inp.batting) delete r.errors;
  for (const r of inp.livelog) { delete r.catcher_acnt; delete r.defend_station_code; }
  assert.deepEqual(news(inp), []);
  assert.ok(errorEvents(inp).events.every((e) => e.playerAcnt === null || ["P"].includes(e.position)));
});

test("守位候選不唯一 ⇒ 不歸屬；歸屬次數超過 box errors ⇒ 不明", () => {
  const two = clone("E4");
  const ev = errorEvents(two).events.find((e) => e.playerAcnt && !["P", "C"].includes(e.position))!;
  const other = two.batting.find((r) => String(r.visiting_home_type) === ev.fieldingSide && String(r.hitter_acnt) !== ev.playerAcnt)!;
  other.errors = 1;
  two.livelog.push({ ...two.livelog.find((r) => String(r.hitter_acnt) === String(other.hitter_acnt))!, defend_station_code: ev.position,
    content: "好球沒揮棒。", main_event_no: "9999999999" });
  assert.equal(errorEvents(two).events.find((e) => e.rowIndex === ev.rowIndex)!.playerAcnt, null);
  const over = clone("E4");
  for (const r of over.batting) if (String(r.hitter_acnt) === ev.playerAcnt) r.errors = 0;
  assert.equal(errorEvents(over).events.find((e) => e.rowIndex === ev.rowIndex)!.playerAcnt, null);
  assert.deepEqual(news(over), []);
});

test("一棒追平：落後時全壘打追平才標；完賽前（completed=false）新標籤都不出", () => {
  const inp = clone("C2");
  // 讓三分砲前已落後 2 分（客隊先得 3 分）：打席前 0–3 落後 → 打席後 3–3 平手 ⇒ 一棒追平、不是逆轉
  for (const r of inp.livelog) if (r.visiting_score != null && Number(r.visiting_score) >= 1) r.visiting_score = Number(r.visiting_score) + 2;
  const t = news(inp).map((h) => h.text);
  assert.ok(t.includes("曾聖安 一棒追平") && !t.includes("曾聖安 一棒逆轉"), t.join("/"));
  assert.deepEqual(news(FX.input.C2, false), []);
});

test("上限 16（需求方批次 F 裁定，原 12）：超過時只留前 16 個、順序不變", () => {
  const inp = clone("E1");
  // 合成 box 列：每位打者 3 安各產生一個「猛打賞」（只驗上限機制，不是資料主張）
  inp.batting = Array.from({ length: 20 }, (_, i) => ({ ...inp.batting[0], hitter_acnt: `X${i}`, hitter_name: `打者${i}`,
    hits: 3, home_runs: 0, grand_slam: 0, rbi: 0, sb: 0 }));
  const all = buildHighlights(inp, true);
  assert.equal(all.length, 16);
  const hit3 = all.filter((h) => h.text.endsWith("猛打賞")).map((h) => h.text);
  assert.deepEqual(hit3, hit3.slice().sort((a, b) => Number(a.match(/\d+/)![0]) - Number(b.match(/\d+/)![0])));
});

// —— review-15 反例（審核者 reviewer-evidence/review-regressions.test.ts 移入；plan-7 r2）——————————————————————————

test("review-15 R1：打席前落後，但全壘打之前已因暴投追平 ⇒ 陽春砲不是一棒逆轉（取全壘打那一列的前後比分）", () => {
  const r = (home_score: number, action_name: string, content: string) => ({ hitter_acnt: "H", hitter_name: "打者", inning_seq: 9,
    visiting_home_type: "2", visiting_score: 1, home_score, action_name, content });
  const d = { game: { away_team_code: "ACN011", home_team_code: "AAA011", away_score: 1, home_score: 2 }, batting: [], pitching: [],
    scoreboard: [], livelog: [
      { ...r(0, "好球", "好球沒揮棒。"), hitter_acnt: "A", visiting_home_type: "1" }, r(0, "好球", "好球沒揮棒。"),
      r(1, "暴投", "投手暴投。三壘跑者跑者甲回本壘得分。"), r(2, "全壘打", "擊出全壘打。1分打點。")] } as unknown as HighlightInput;
  assert.ok(!buildHighlights(d, true).some((h) => h.text.includes("一棒逆轉")));
});

test("review-15 R2：失誤者不唯一（playerAcnt＝null）⇒ 致命失誤也不標（6259751815 時點或歸屬不明一律不標）", () => {
  const d = clone("C2");
  const ev = errorEvents(d).events.find((e) => e.inning === 5 && e.position === "1B")!;
  const other = d.batting.find((r) => String(r.visiting_home_type) === ev.fieldingSide && String(r.hitter_acnt) !== ev.playerAcnt)!;
  other.errors = 1;
  d.livelog.find((r) => String(r.hitter_acnt) === String(other.hitter_acnt))!.defend_station_code = "1B";
  assert.equal(errorEvents(d).events.find((e) => e.rowIndex === ev.rowIndex)!.playerAcnt, null);
  assert.ok(!buildHighlights(d, true).some((h) => h.text === "兄弟 致命失誤（5 局）"));
});
