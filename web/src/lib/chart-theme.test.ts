import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// H4 防 drift 守門：zone/status 有雙定義——canonical＝globals.css `@theme` 的 `--zone-*`/`--status-*`
// 淺色 token；chart-theme.ts 的 LIGHT_FALLBACK（SSR/首繪前退場）與 STATUS_COLORS 常數盤是其鏡像。
// 本測試以純文字比對確保兩處淺色值一致，任一端單改即失敗。（深色由 [data-theme=dark] 覆寫，不在此比對。）
const globals = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const chart = readFileSync(new URL("./chart-theme.ts", import.meta.url), "utf8");
const H = "([0-9a-fA-F]{6})";

// globals.css @theme 淺色值＝各 token 第一次出現（@theme 區塊在 [data-theme=dark] 覆寫之前）。
const cssVar = (name: string): string => {
  const m = globals.match(new RegExp(`--${name}:\\s*#${H}`));
  assert.ok(m, `globals.css 缺 --${name}`);
  return m[1].toLowerCase();
};

test("chart-theme LIGHT_FALLBACK.zone 鏡像 globals.css @theme --zone-* 淺色（防 drift）", () => {
  const m = chart.match(
    new RegExp(`zone:\\s*\\{\\s*heart:\\s*"#${H}",\\s*shadow:\\s*"#${H}",\\s*chase:\\s*"#${H}",\\s*waste:\\s*"#${H}"`),
  );
  assert.ok(m, "chart-theme.ts 找不到 LIGHT_FALLBACK.zone 字面值");
  assert.equal(m[1].toLowerCase(), cssVar("zone-heart"));
  assert.equal(m[2].toLowerCase(), cssVar("zone-shadow"));
  assert.equal(m[3].toLowerCase(), cssVar("zone-chase"));
  assert.equal(m[4].toLowerCase(), cssVar("zone-waste"));
});

test("chart-theme LIGHT_FALLBACK.status 與 STATUS_COLORS 皆鏡像 globals.css @theme --status-* 淺色（防 drift）", () => {
  const want = {
    import: cssVar("status-import"),
    loree: cssVar("status-loree"),
    nagata: cssVar("status-nagata"),
  };
  const fb = chart.match(new RegExp(`status:\\s*\\{\\s*import:\\s*"#${H}",\\s*loree:\\s*"#${H}",\\s*nagata:\\s*"#${H}"`));
  assert.ok(fb, "找不到 LIGHT_FALLBACK.status 字面值");
  assert.equal(fb[1].toLowerCase(), want.import);
  assert.equal(fb[2].toLowerCase(), want.loree);
  assert.equal(fb[3].toLowerCase(), want.nagata);
  const sc = chart.match(new RegExp(`STATUS_COLORS[\\s\\S]*?import:\\s*"#${H}",\\s*loree:\\s*"#${H}",\\s*nagata:\\s*"#${H}"`));
  assert.ok(sc, "找不到 STATUS_COLORS 字面值");
  assert.equal(sc[1].toLowerCase(), want.import);
  assert.equal(sc[2].toLowerCase(), want.loree);
  assert.equal(sc[3].toLowerCase(), want.nagata);
});
