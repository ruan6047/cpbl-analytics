/**
 * 結構守衛：一個畫面上的賽前機率與其 serving 狀態必須來自**同一份 response**。
 *
 * ML-OUTCOME-SIMPLE-LEAK2 的同一個結構問題連續三輪換位置重現（serving 一致性 → 誤報成因
 * → 快取 → 首頁跨 response 競態），共同成因都是「兩個必須一致的事實，來自不同來源／不同
 * 新鮮度」。前幾輪都靠再加一個判斷收尾，所以又長回來。
 *
 * 這裡改成守住結構本身：渲染頁面不得再去取那支獨立的 serving 端點——它只留給上線程序的
 * ops 對帳。純函式測試（daily-summary.test.ts）守住行為，這支守住「不會再有第二個來源」。
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const SRC = path.join(import.meta.dirname, "..");

function read(relative: string): string {
  return readFileSync(path.join(SRC, relative), "utf8");
}

/** 渲染賽前機率或其狀態的檔案；新增同類頁面時一併加進來。 */
const RENDERING_SOURCES = [
  "app/page.tsx",
  "components/daily-hub.tsx",
  "app/methodology/page.tsx",
];

test("渲染頁面不得取用獨立的 serving 端點（那是 ops 探針，不是第二個渲染來源）", () => {
  for (const file of RENDERING_SOURCES) {
    // 只抓 api.pregameServing() 這個「取第二份 response」的呼叫；
    // pregameServingNotice 是純文案函式（不發請求），不在此限。
    assert.equal(
      /\bapi\.pregameServing\s*\(/.test(read(file)),
      false,
      `${file} 不得呼叫 api.pregameServing()：` +
        "首頁的狀態要從 dailySummary 取、方法頁從 pregameBacktest 取，" +
        "各自與它要描述的數字同源。",
    );
  }
});

test("DailyHub 不得開放外部注入 serving 狀態", () => {
  const source = read("components/daily-hub.tsx");

  assert.equal(
    /serving\??:/.test(source),
    false,
    "DailyHub 只能吃一份 summary；開 serving prop 等於再開一次雙來源的洞",
  );
  assert.ok(
    source.includes("homePregameNotice"),
    "告示必須走只收 DailySummary 的 homePregameNotice",
  );
});

test("首頁聚合契約必須是不進快取的取用", () => {
  // dailySummary 同時帶點機率與 serving 版本；一旦被快取，就會與任何即時來源錯開。
  const api = read("lib/api.ts");
  const call = api.slice(api.indexOf("dailySummary:"));

  assert.ok(
    call.slice(0, 300).includes("getLive<DailySummary>"),
    "dailySummary 必須走 getLive（no-store）：它同時承載機率與 serving 狀態",
  );
});
