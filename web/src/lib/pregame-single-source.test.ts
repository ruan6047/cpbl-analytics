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

/** 渲染賽前機率或其狀態的檔案；新增同類頁面時一併加進來。
 *  賽況頁（games/[sno]）是第三個介面——開卡時 scope 沒寫全，iteration 5 才補上。 */
const RENDERING_SOURCES = [
  "app/page.tsx",
  "components/daily-hub.tsx",
  "app/methodology/page.tsx",
  "app/games/[sno]/page.tsx",
  "components/pregame-card.tsx",
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

test("PregameCard 的告示只能由 view model 帶進來，不得自行取用或接受外部注入", () => {
  const component = read("components/pregame-card.tsx");

  // 元件契約本來就是「純展示、不抓資料」；告示也必須遵守，否則就成了第二個來源。
  assert.equal(
    /\bfetch\s*\(|clientGet|useEffect/.test(component),
    false,
    "pregame-card.tsx 不得自行抓資料——告示與機率同由 resolvePregameCard 產出",
  );
  assert.ok(
    component.includes("model.servingNotice"),
    "卡片必須渲染 view model 上的 servingNotice",
  );
  assert.equal(
    /servingNotice\??:\s*string/.test(component),
    false,
    "不得把 servingNotice 開成獨立 prop：那等於允許從 model 以外注入",
  );
});

test("賽況頁把整份 response 交給 resolver，不自行挑欄位", () => {
  // 機率與 serving 狀態同在 /api/v1/outcome/pregame 這一份 response 內；
  // 只要整份傳進 resolver，單一來源不變式就是結構性的，不靠紀律維持。
  const page = read("app/games/[sno]/page.tsx");

  assert.ok(page.includes("resolvePregameCard({"), "賽況頁必須走 resolvePregameCard");
  assert.ok(
    /\.then\(\(response\) => setPregame\(resolvePregameCard\(\{\s*\n\s*response,/.test(page),
    "必須整份 response 傳入（不得只挑 items 而漏掉 serving）",
  );
});

test("方法頁的告示出自 backtest 那一份 response，且走共用的 pregameServingNotice", () => {
  // 方法頁是第二個介面。它顯示的是那張回測表，故 serving 狀態必須取自同一份 backtest
  // response；文案則與首頁／賽況頁共用同一支函式，三處才不會各講各的
  //（三個介面的文案行為由 daily-summary.test.ts 與 pregame-card.test.ts 覆蓋）。
  const page = read("app/methodology/page.tsx");

  assert.ok(
    page.includes("backtest.serving ??"),
    "serving 狀態必須來自 backtest 這一份 response（不得另外請求）",
  );
  assert.ok(
    page.includes("pregameServingNotice(servingMeta)"),
    "文案必須走共用函式，不得在頁面內另寫一套 degradation 分流",
  );
  assert.equal(
    /degradation\s*===/.test(page),
    false,
    "頁面不得自行判讀 degradation：判別在後端做一次、文案在 pregameServingNotice 做一次",
  );
});

test("resolvePregameCard 由 response.serving 推導告示，不引入第二來源", () => {
  const lib = read("lib/pregame-card.ts");

  assert.ok(
    lib.includes("response.serving ? pregameServingNotice(response.serving) : null"),
    "告示必須來自傳入的那一份 response",
  );
  assert.equal(
    /\bfetch\s*\(|clientGet/.test(lib),
    false,
    "pregame-card.ts 是純解析模組，不得自行發請求",
  );
});
