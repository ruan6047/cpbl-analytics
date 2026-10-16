import assert from "node:assert/strict";
import test from "node:test";

import { overviewPath, parseSeriesParam, seriesHref, watchPath } from "./playoffs-types.ts";

// #285 批次 B WP-S2：`/playoffs?series=E|C` 的網址解析與連結。

test("parseSeriesParam 只收大寫 E／C，其他一律視為未指定", () => {
  assert.equal(parseSeriesParam("E"), "E");
  assert.equal(parseSeriesParam("C"), "C");
  for (const v of [undefined, "", "e", "c", "A", "EC", " E", ["E"], ["E", "C"]]) {
    assert.equal(parseSeriesParam(v as string | string[] | undefined), null, JSON.stringify(v));
  }
});

test("overviewPath：未指定系列時與原網址相同；指定才帶 series", () => {
  assert.equal(overviewPath(2026), "/api/v1/playoffs/overview?season=2026");
  assert.equal(overviewPath(2026, null), "/api/v1/playoffs/overview?season=2026");
  assert.equal(overviewPath(2026, "E"), "/api/v1/playoffs/overview?season=2026&series=E");
  assert.equal(watchPath(2026, "E", 4), "/api/v1/playoffs/watch?season=2026&series=E&game=4");
});

test("seriesHref：保留網址上的 year、拿掉 game", () => {
  assert.equal(seriesHref("E", null), "/playoffs?series=E");
  assert.equal(seriesHref("C", 2025), "/playoffs?year=2025&series=C");
  assert.doesNotMatch(seriesHref("E", 2026), /game=/);
});
