import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildHighlights, UMPIRE_CALL_WORD, type HighlightInput } from "./game-highlights.ts";
import { highlightsRows, type HighlightsPayload } from "./playoffs-series-highlights.ts";

// #285 批次 G 判決標籤：後端已判定（umpire_call），前端只排字。夾具＝2026 季後六場真實投影（批次 F）。
const FX = JSON.parse(readFileSync(new URL("./__fixtures__/game-highlights_2026-batchF.json", import.meta.url), "utf8")) as {
  input: Record<string, HighlightInput>;
};
const WORDS = new Set(Object.values(UMPIRE_CALL_WORD));
const umps = (inp: HighlightInput, completed = true) => buildHighlights(inp, completed).filter((h) => WORDS.has(h.text));

test("有後端結果 ⇒ 一個 chip，字樣只寫該隊的詞、印記＝得利隊；E3 獅捨、C1 成全", () => {
  assert.deepEqual(umps({ ...FX.input.E3, umpire_call: { team_code: "ADD011" } }), [{ text: "獅捨", team: "ADD011" }]);
  assert.deepEqual(umps({ ...FX.input.C1, umpire_call: { team_code: "AAA011" } }), [{ text: "成全", team: "AAA011" }]);
  assert.deepEqual(Object.entries(UMPIRE_CALL_WORD).sort(), [
    ["AAA011", "成全"], ["ACN011", "識象"], ["ADD011", "獅捨"], ["AEO011", "邦忙"], ["AJL011", "猿夢"], ["AKP011", "鷹明"]]);
});

test("null／未給／未完賽 ⇒ 不出；歷史隊碼依 franchise 對應", () => {
  assert.deepEqual(umps({ ...FX.input.E3, umpire_call: { team_code: null } }), []);
  assert.deepEqual(umps(FX.input.E3), []);
  assert.deepEqual(umps({ ...FX.input.E3, umpire_call: { team_code: "ADD011" } }, false), []);
  assert.deepEqual(umps({ ...FX.input.E3, umpire_call: { team_code: "AJK011" } }), [{ text: "猿夢", team: "AJK011" }]);
});

test("排在稀有組、批次 F 新標籤之後；不影響既有與批次 F 標籤", () => {
  const base = buildHighlights(FX.input.C2, true).map((h) => h.text);
  const withTag = buildHighlights({ ...FX.input.C2, umpire_call: { team_code: "ACN011" } }, true).map((h) => h.text);
  assert.deepEqual(withTag.filter((t) => t !== "識象"), base);
  assert.equal(withTag.indexOf("識象"), withTag.indexOf("兄弟 致命失誤（5 局）") + 1);
});

test("/playoffs 列模型：每場 umpire_call 併進 input 交同一個 buildHighlights", () => {
  const data = { contract: "playoffs-highlights/v1", context_version: "v", series: "E", series_id: {}, as_of: {}, status: "ok",
    games: [{ series_game_no: 3, game_key: { year: 2026, kind_code: "E", game_sno: 3 }, data_status: "ok", input: FX.input.E3,
      umpire_call: { team_code: "ADD011", reason: null } }] } as unknown as HighlightsPayload;
  const [row] = highlightsRows(data);
  assert.ok(row.tags.some((t) => t.text === "獅捨" && t.team === "ADD011"));
});
