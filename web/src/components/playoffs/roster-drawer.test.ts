import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// #415：`/playoffs` 首載不得帶 recharts。抽屜只能以 `import("./roster-charts")` 按需取圖表模組；
// 任何對圖表進入點（roster-charts／ability-card／players trend）的靜態 import 都會讓 webpack 把 recharts
// 併回首載 chunk（研究 §4：改前 6 個 recharts chunk 合計約 121 kB gzip）。抽屜本身用 createPortal(document.body)
// 無法在 node 內 SSR，故在模組圖層級守住這條（同 live-game.test.ts 讀原文斷言的作法）。
const src = readFileSync(new URL("./roster-drawer.tsx", import.meta.url), "utf8");
const staticImports = [...src.matchAll(/^import\b[^;]*?from\s+"([^"]+)"/gm)].map((m) => m[1]);

test("roster-drawer：不靜態 import 圖表進入點，只以 import() 取 roster-charts", () => {
  for (const spec of staticImports) {
    assert.doesNotMatch(spec, /roster-charts|ability-card|players\/\[id\]\/trend|^recharts$/, `靜態 import：${spec}`);
  }
  assert.match(src, /import\("\.\/roster-charts"\)/);
});
