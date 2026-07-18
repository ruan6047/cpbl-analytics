import assert from "node:assert/strict";
import test from "node:test";

import { METHODOLOGY_SECTIONS } from "./methodology-anchors.ts";
import {
  METHODOLOGY_CONTENT,
  NOT_ON_SITE,
  SECTION_IDS,
} from "./methodology-content.ts";

test("內容覆蓋 anchor 契約的全部五段，不多不少", () => {
  assert.deepEqual(Object.keys(METHODOLOGY_CONTENT), Object.keys(METHODOLOGY_SECTIONS));
  assert.deepEqual(SECTION_IDS, Object.keys(METHODOLOGY_SECTIONS));
});

test("每段六欄齊備且非空（§5.14：問題／期間／baseline／validation／限制／版本）", () => {
  for (const [id, entry] of Object.entries(METHODOLOGY_CONTENT)) {
    assert.ok(entry.question.length > 0, `${id} 缺回答的問題`);
    assert.ok(entry.period.length > 0, `${id} 缺資料期間`);
    assert.ok(entry.baseline.length > 0, `${id} 缺 baseline`);
    assert.ok(entry.validation.length > 0, `${id} 缺 validation`);
    assert.ok(entry.limits.length > 0, `${id} 缺限制`);
    assert.ok(entry.version.length > 0, `${id} 缺版本`);
  }
});

test("區間紅線：全文只允許以否定句「並非統計信賴區間」提及信賴區間", () => {
  const corpus = JSON.stringify(METHODOLOGY_CONTENT) + JSON.stringify(NOT_ON_SITE);
  const stripped = corpus.replaceAll("並非統計信賴區間", "");
  assert.equal(stripped.includes("信賴區間"), false);
  // 賽前勝率的區間必須以固定名稱「模型敏感度區間」出現（與 pregame-card 紅線一致）。
  assert.ok(JSON.stringify(METHODOLOGY_CONTENT.pregame).includes("模型敏感度區間"));
});

test("no-go 邊界：未上線模型不得出現能力暗示字眼", () => {
  const corpus = JSON.stringify(NOT_ON_SITE);
  for (const banned of ["即將", "敬請期待", "coming soon", "預計上線"]) {
    assert.equal(corpus.includes(banned), false, `不得出現「${banned}」`);
  }
});
