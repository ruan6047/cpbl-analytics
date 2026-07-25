// 共用對戰面板的資料獲取結構守衛。
// 這裡守的是「哪個查詢餵哪個 UI」——純函式測試（controls.test.ts）只能驗可選集合的
// 計算規則，無法驗出「交手清單是用帶隊別篩選的查詢算出來的」這種資料流缺陷。
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const explorer = readFileSync(new URL("./explorer.tsx", import.meta.url), "utf8");

/** 交手球隊清單（faced）的 effect 區段。 */
function facedEffect(): string {
  const start = explorer.indexOf("const [faced, setFaced]");
  const end = explorer.indexOf("}, [pid, query]);", start);
  assert.ok(start > 0 && end > start, "找不到 faced effect 區段");
  return explorer.slice(start, end);
}

test("交手球隊清單以不帶隊別篩選的查詢推導", () => {
  const effect = facedEffect();
  // 缺陷版是 `.list(pid, query, { team })`：一旦選了隊，清單只剩該隊或整批消失，
  // 下拉就退回全部球隊（含已解散隊）。
  assert.match(effect, /\.list\(pid, query\)/);
  assert.ok(!effect.includes("team"), "faced 查詢與其 effect 不得涉及 team");
});

test("顯示用的對手清單仍套用隊別、排序與筆數（兩個查詢職責不混用）", () => {
  const listCall = explorer.match(/\.list\(pid, query, \{[^}]*\}\)/g) ?? [];
  assert.equal(listCall.length, 1, "只有顯示用清單可帶篩選參數");
  assert.match(listCall[0], /team/);
  assert.match(listCall[0], /sort/);
  assert.match(listCall[0], /order/);
});

test("可選集合計算走 controls 的單一來源，不在元件內重寫 filter", () => {
  assert.match(explorer, /visibleOpponentFranchises\(franchises, facedCodes, team\)/);
  assert.ok(
    !explorer.includes("franchises.filter("),
    "元件內不得另寫一份可選集合過濾邏輯",
  );
});
