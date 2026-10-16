import assert from "node:assert/strict";
import test from "node:test";
import { parsePlayoffsSelection, legacyPlayoffsLocation } from "./playoffs-selection.ts";

test("原生預設與明確身分分開，官方場號不假定 1–7", () => {
  assert.deepEqual(parsePlayoffsSelection({}), { valid: true, year: null, series: null, game: null, revision: null });
  assert.deepEqual(parsePlayoffsSelection({ year: "2024", series: "E", game: "901", revision: "old/a" }),
    { valid: true, year: 2024, series: "E", game: 901, revision: "old/a" });
});
test("非法、空與重複身分不能掉回預設", () => {
  for (const [key, values] of Object.entries({ year: ["", "1989", "2101", "2026.0", ["2026", "2026"]],
    series: ["", "e", "A", ["E", "C"]], game: ["", "bad", "0", "-1", "1.5", "9007199254740992", ["1", "2"]],
    revision: ["", " ", ["a", "b"]] })) {
    for (const value of values) assert.equal(parsePlayoffsSelection({ [key]: value }).valid, false, `${key}=${value}`);
  }
});
test("舊址保留 X、重複與缺少必要參數，版本安全編碼且所有 tab 落 watch", () => {
  for (const tab of ["overview", "pitchers", "fielders"]) {
    assert.equal(legacyPlayoffsLocation("1", new URLSearchParams(`year=2026&kind=E&tab=${tab}&revision=a%26b&next=9`)),
      "/playoffs?year=2026&series=E&game=1&revision=a%26b#watch");
  }
  assert.equal(legacyPlayoffsLocation("bad", new URLSearchParams()), "/playoffs?year=&series=&game=bad#watch");
  assert.equal(legacyPlayoffsLocation("2", new URLSearchParams("year=2024&year=2025&kind=E&kind=C&revision=a&revision=b")),
    "/playoffs?year=2024&year=2025&series=E&series=C&game=2&revision=a&revision=b#watch");
});
