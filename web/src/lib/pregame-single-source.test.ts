/**
 * 結構守衛：一個畫面上的賽前機率與其 serving 狀態必須來自**同一份 response**。
 *
 * ML-OUTCOME-SIMPLE-LEAK2 的同一個結構問題連續三輪換位置重現（serving 一致性 → 誤報成因
 * → 快取 → 首頁跨 response 競態），共同成因都是「兩個必須一致的事實，來自不同來源／不同
 * 新鮮度」。前幾輪都靠再加一個判斷收尾，所以又長回來。
 *
 * ## 量詞方向（UX-PREGAME-SOURCE-GUARD1）
 *
 * 舊版守衛是「對每個渲染介面，斷言它不做 X」，需要一份手寫的 `RENDERING_SOURCES` 清單。
 * 那份清單漏列即靜默失效，而且真的漏過一次（賽況頁 `games/[sno]` 是第三個介面，開卡時
 * scope 沒寫全，iteration 5 才補上）。「漏列就靜默失效」的守衛，正是它自己要防的缺陷。
 *
 * 所以量詞反過來寫：**在整個 `web/src` 裡，X 只准出現在指定的幾個位置**。新檔案一存在
 * 就自動被涵蓋，因為規則列舉的是例外（allowlist），不是主體。清單不得以任何形式復活。
 *
 * 兩條全域規則：
 *   規則 1｜第二來源不可達：serving 端點路徑不得出現在 `web/src` 任何地方（無例外）。
 *   規則 2｜機率只有一條推導路徑：`home_win_probability` 只准在三個 lib 檔被讀。
 *
 * 比對前先剝掉註解（見 `stripComments`）：上一輪踩過「註解裡提到就誤判」的假陽性，而本檔
 * 之外的檔案（如 `lib/api.ts`）確實需要在註解裡說明「為什麼刻意沒有這支 client method」。
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const SRC = path.join(import.meta.dirname, "..");

function read(relative: string): string {
  return readFileSync(path.join(SRC, relative), "utf8");
}

/**
 * 剝掉 `//` 行註解與 `/* *\/` 區塊註解，但**不能**把字串裡的 `//`（如 `"https://…"`）
 * 誤判成註解——誤判會把該行後面的真實程式碼一起吃掉，變成假陰性。故用字元掃描追蹤
 * 字串／樣板字面值狀態，而不是單純 regex 取代。
 *
 * 正規表示式字面值不特別處理：`//` 是行註解、`/*` 在 regex 開頭不合法，
 * 而 regex 內部的斜線一律轉義（`\/`），不會出現相鄰的未轉義 `//`。
 */
export function stripComments(source: string): string {
  let out = "";
  let i = 0;
  while (i < source.length) {
    const c = source[i];
    const next = source[i + 1];

    if (c === "/" && next === "/") {
      while (i < source.length && source[i] !== "\n") i += 1;
      continue;
    }
    if (c === "/" && next === "*") {
      i += 2;
      while (i < source.length && !(source[i] === "*" && source[i + 1] === "/")) {
        // 保留換行，行號才不會位移
        if (source[i] === "\n") out += "\n";
        i += 1;
      }
      i += 2;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      out += c;
      i += 1;
      while (i < source.length) {
        if (source[i] === "\\") {
          out += source.slice(i, i + 2);
          i += 2;
          continue;
        }
        out += source[i];
        if (source[i] === quote) {
          i += 1;
          break;
        }
        i += 1;
      }
      continue;
    }

    out += c;
    i += 1;
  }
  return out;
}

/** `web/src` 底下所有會被打包進 app 的原始碼（相對 `SRC` 的 posix 路徑）。
 *  排除 `*.test.ts(x)`：測試不是渲染介面、不進 bundle，且必須能構造 payload 與
 *  在本檔寫出規則字面值本身。這是**類別**排除，不是檔案清單——新增測試自動適用。 */
function sourceFiles(): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(path.join(SRC, dir), { withFileTypes: true })) {
      const rel = dir ? `${dir}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        walk(rel);
      } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
        found.push(rel);
      }
    }
  };
  walk("");
  return found.sort();
}

test("掃描面涵蓋整個 web/src（不只 app/ 與 components/）", () => {
  const files = sourceFiles();

  // 錨點：三個渲染介面、共用元件、以及 lib/（舊守衛的盲點——新的 lib 檔案同樣危險）。
  for (const anchor of [
    "app/page.tsx",
    "app/methodology/page.tsx",
    "app/games/[sno]/page.tsx",
    "components/daily-hub.tsx",
    "components/pregame-card.tsx",
    "lib/api.ts",
    "lib/client.ts",
  ]) {
    assert.ok(files.includes(anchor), `掃描面必須涵蓋 ${anchor}`);
  }
  assert.ok(files.length > 80, `掃描面過小（${files.length}），walk 可能壞了`);
  assert.equal(
    files.some((f) => /\.test\.tsx?$/.test(f)),
    false,
    "測試檔應被排除",
  );
});

// —— 規則 1：第二來源不可達 ——
//
// serving 狀態的獨立端點只留給上線程序的 curl 對帳。web 端沒有任何 client method 可以取它
// （UX-PREGAME-SOURCE-GUARD1 已從 lib/api.ts 刪掉 `pregameServing`），要取就得自己寫出這段
// 路徑——本規則直接擋在路徑上，故不論走 api.ts、clientGet 還是裸 fetch 都會被抓到。
const SERVING_ENDPOINT = "/api/v1/outcome/pregame/serving";

test("規則 1：serving 端點路徑不得出現在 web/src 任何位置（無例外）", () => {
  const offenders = sourceFiles().filter((file) =>
    stripComments(read(file)).includes(SERVING_ENDPOINT),
  );

  assert.deepEqual(
    offenders,
    [],
    `${SERVING_ENDPOINT} 是 ops 探針，不是第二個渲染來源：` +
      "頁面的 serving 狀態要與它描述的數字同源（首頁走 dailySummary、方法頁走 " +
      "pregameBacktest、賽況頁走 pregame 那一份 response）。",
  );
});

// —— 規則 2：機率只有一條推導路徑 ——
//
// 規則 1 只擋住 serving 狀態。真正危險的新頁面是**不 import 任何共用 symbol**、自己打
// api/client 的 pregame 端點、直接讀 `item.home_win_probability` 渲染的那種——它對
// 「有沒有 import resolvePregameCard」的掃描完全隱形，但對本規則不隱形。
const PROBABILITY_FIELD = "home_win_probability";
/** 唯二的 resolver 與它們的假資料。這是**例外**清單，不是渲染介面清單。 */
const PROBABILITY_READERS = [
  "lib/pregame-card.ts",
  "lib/daily-summary.ts",
  "lib/pregame-card-fixtures.ts",
];

test(`規則 2：${PROBABILITY_FIELD} 只准在三個 resolver／fixture 檔出現`, () => {
  const pattern = new RegExp(`\\b${PROBABILITY_FIELD}\\b`);
  const offenders = sourceFiles().filter(
    (file) => !PROBABILITY_READERS.includes(file) && pattern.test(stripComments(read(file))),
  );

  assert.deepEqual(
    offenders,
    [],
    `${PROBABILITY_FIELD} 只能由 ${PROBABILITY_READERS.join("／")} 讀：` +
      "頁面與元件一律吃 resolvePregameCard／resolvePregameFromDaily 產出的 view model，" +
      "自己解一次機率就會出現第二條推導路徑（缺值、四捨五入、降級判定各走各的）。",
  );
});

test("規則 2 的 allowlist 必須真的都還在讀（清單不得留下死條目）", () => {
  const pattern = new RegExp(`\\b${PROBABILITY_FIELD}\\b`);
  for (const file of PROBABILITY_READERS) {
    assert.ok(
      pattern.test(stripComments(read(file))),
      `${file} 已不再讀 ${PROBABILITY_FIELD}，請從 allowlist 移除（例外只保留仍需要的）`,
    );
  }
});

test("stripComments：剝註解不得吃掉字串裡的網址或真實程式碼", () => {
  assert.equal(stripComments('const u = "https://a.b/c"; // note\nx'), 'const u = "https://a.b/c"; \nx');
  assert.equal(stripComments("a /* b\nc */ d"), "a \n d");
  assert.equal(stripComments('f("http://x"); g(item.home_win_probability);').includes("home_win_probability"), true);
  // 註解裡提到欄位名不算違規（lib/api.ts 就需要在註解裡說明為什麼刻意沒有那支 method）
  assert.equal(stripComments("// home_win_probability\n").includes("home_win_probability"), false);
  assert.equal(stripComments("/* /api/v1/outcome/pregame/serving */").trim(), "");
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
