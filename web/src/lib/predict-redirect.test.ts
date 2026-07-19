import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { methodologyHref } from "./methodology-anchors.ts";

test("舊 /predict 路由只導向賽前方法段落", () => {
  const page = readFileSync(new URL("../app/predict/page.tsx", import.meta.url), "utf8");

  assert.equal(methodologyHref("pregame"), "/methodology#pregame");
  assert.match(page, /redirect\(methodologyHref\("pregame"\)\)/);
  assert.doesNotMatch(page, /outcome\/(features|evaluate|matchups|simulate)/);
});
