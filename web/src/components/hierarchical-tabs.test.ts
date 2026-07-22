import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./hierarchical-tabs.tsx", import.meta.url), "utf8");

test("階層導覽三種控制的觸控目標皆至少 44px", () => {
  const targets = source.match(/className={`min-h-11/g) ?? [];
  assert.equal(targets.length, 3, "母標籤、情境切換與子頁籤都應使用 min-h-11");
  assert.doesNotMatch(source, /className={`min-h-(?:8|9|10)\b/);
});
