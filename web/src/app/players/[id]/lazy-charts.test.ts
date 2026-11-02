import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// #415：球員頁首載不得帶 recharts。recharts 主體 chunk 只要有任何一個靜態進入點留著就仍在首載，
// 故 `page.tsx` 的靜態圖（trend／parts／hero→ability-card）與 `ability-card.tsx` 只能以 `import()` 取圖表模組；
// 連「只為了拿常數」的靜態 import 也不行——ES 模組會整個載入（含它的 recharts import）。
// `import type …` 會被擦除，不算。
const FILES = ["./page.tsx", "./trend.tsx", "./parts.tsx", "./hero.tsx", "./season.tsx", "./detail.tsx", "../../../components/ability-card.tsx"];
const CHART_MODULES = /^recharts$|trend-chart|composition-pie|ability-radar|^\.\/tracking$/;
const staticImports = (src: string) =>
  [...src.matchAll(/^import\b(?!\s+type\b)[^;]*?from\s+"([^"]+)"/gm)].map((m) => m[1]);

for (const f of FILES) {
  test(`${f}：不靜態 import recharts 或圖表模組`, () => {
    const src = readFileSync(new URL(f, import.meta.url), "utf8");
    for (const spec of staticImports(src)) assert.doesNotMatch(spec, CHART_MODULES, `${f} 靜態 import：${spec}`);
  });
}

test("圖表模組以 import() 按需載入", () => {
  assert.match(readFileSync(new URL("./trend.tsx", import.meta.url), "utf8"), /import\("\.\/trend-chart"\)/);
  assert.match(readFileSync(new URL("./page.tsx", import.meta.url), "utf8"), /import\("\.\/tracking"\)/);
  assert.match(readFileSync(new URL("../../../components/ability-card.tsx", import.meta.url), "utf8"), /import\("\.\/ability-radar"\)/);
});
