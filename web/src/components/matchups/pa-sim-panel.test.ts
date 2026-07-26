import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";

// 版面契約以原始碼守衛（同 hierarchical-tabs.test.ts 模式）：這些是「首版邊界」與
// 「fail-closed 不被繞過」的結構性條件，行為測試無法在無 DOM 環境重現。
const panel = readFileSync(new URL("./pa-sim-panel.tsx", import.meta.url), "utf8");
const explorer = readFileSync(new URL("./explorer.tsx", import.meta.url), "utf8");

/** web/src 下所有 tsx；用來掃描共用 explorer 的**全部**消費者，不寫死檔名
    （寫死檔名會讓「換一個整合點就繞過邊界」的回歸靜默通過）。 */
const SRC_ROOT = new URL("../../", import.meta.url);
function explorerConsumers(): { path: string; source: string }[] {
  return readdirSync(SRC_ROOT, { recursive: true, encoding: "utf8" })
    .filter((entry) => entry.endsWith(".tsx"))
    .map((entry) => ({ path: entry, source: readFileSync(new URL(entry, SRC_ROOT), "utf8") }))
    .filter((file) => file.source.includes("<MatchupExplorer"));
}

test("第二 tab 只在選定具體打者×投手的分支存在（驗收條件 1）", () => {
  // 精確界出三個互斥分支：!pid（未選主角）／pid && opp（單組對決）／pid && !opp（清單）。
  const pairIndex = explorer.indexOf("{pid && opp && (");
  const listIndex = explorer.indexOf("{pid && !opp && (");
  assert.ok(pairIndex > 0 && listIndex > pairIndex, "explorer 分支順序與預期不符");
  const pairBranch = explorer.slice(pairIndex, listIndex);
  const outsidePairBranch = explorer.slice(0, pairIndex) + explorer.slice(listIndex);

  assert.ok(pairBranch.includes("<PaSimPanel"), "模擬面板應在單組對決分支內");
  // 全檔只能有一處渲染，且必須落在單組對決分支（比對 JSX 使用點，import 行不算渲染）。
  assert.equal((explorer.match(/<PaSimPanel/g) ?? []).length, 1);
  assert.ok(!outsidePairBranch.includes("<PaSimPanel"), "單組對決分支之外不得渲染模擬面板");
  assert.ok(!outsidePairBranch.includes("<MainTabs"), "對決檢視 tab 不得出現在其他分支");
  assert.match(pairBranch, /enablePaSim && pairView === "simulation"/);
});

test("歷史實績是預設檢視，換對手／換主角會重置回歷史", () => {
  assert.match(explorer, /useState<PairView>\("history"\)/);
  assert.match(explorer, /setPairView\("history"\), \[pid, opp, role\]/);
});

test("首版只在 /matchups 啟用；其餘整合點不得開啟（blueprint §6 條件採用）", () => {
  assert.match(explorer, /enablePaSim = false/, "prop 預設必須關閉");
  const consumers = explorerConsumers();
  assert.ok(consumers.length >= 2, `應至少有 /matchups 與球員頁兩個消費者，實得 ${consumers.length}`);
  const enabled = consumers.filter((file) => file.source.includes("enablePaSim"));
  assert.deepEqual(
    enabled.map((file) => file.path).sort(),
    ["app/matchups/matchups-client.tsx"],
    "只有 /matchups 可啟用 pa_sim；球員頁等整合點須維持關閉（真實打席入口另卡 UX-GAME-PA1）",
  );
});

test("面板不自行計算機率：只讀 API 欄位，無本地機率運算", () => {
  // 允許的算術只有：視角換算（batterSideWinProbability／batterSideDelta）、
  // 條寬百分比、群組機率加總、百分比格式化。禁止出現任何模型式運算。
  for (const forbidden of ["Math.exp", "Math.log", "Math.pow", "1.645", "Math.sqrt"]) {
    assert.ok(!panel.includes(forbidden), `面板不得自行做統計運算：${forbidden}`);
  }
  // 硬編小數字面值＝可能的預設替代機率（如 0.5）。lookbehind 排除 Tailwind 類名
  // 中的 `-0.5`／`1.5` 這類間距值，只攔獨立的數值常數。
  assert.doesNotMatch(
    panel,
    /(?<![-\w.])0\.\d/,
    "面板不得出現硬編機率字面值（禁補 50% 之類的替代數字）",
  );
});

test("退化態一律走三態元件承載，api_error 與其餘態視覺分流", () => {
  assert.match(panel, /state\.kind === "api_error" \? <ErrorState>/);
  assert.match(panel, /: <EmptyState>/);
  // 不得出現 ad-hoc 空態字串（設計系統 §3.3）
  assert.ok(!panel.includes(">無資料<"));
  assert.ok(!panel.includes("載入中…"));
});

test("退化態內容只用 inline 元素：EmptyState／ErrorState 本體是 <p>", () => {
  // 在 <p> 內放 <div>／<p> 會造成 React hydration error（2026-07-25 真實瀏覽器實測）。
  const start = panel.indexOf("function DegradedState");
  const end = panel.indexOf("export default function PaSimPanel");
  assert.ok(start > 0 && end > start, "找不到 DegradedState 實作區段");
  // 去掉註解行後再比對，否則說明文字裡的 `<p>` 會誤判。
  const degraded = panel
    .slice(start, end)
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
  assert.ok(!/<div\b/.test(degraded), "退化態不得在 <p> 內放 <div>");
  assert.ok(!/<p[\s>]/.test(degraded), "退化態不得在 <p> 內再放 <p>");
  assert.match(degraded, /<span className="mx-auto block/);
});

test("首次載入顯示骨架而非退化態（不得閃現「無法模擬」）", () => {
  // pending 必須把「尚無回應」與「API 明示不可用」分開，否則掛載瞬間會閃錯誤文案。
  assert.match(panel, /const pending = supported && !failed && response === null;/);
  assert.match(panel, /\{pending && \(/);
  assert.match(panel, /\{!pending && derived\.kind !== "ok" && \(/);
  assert.match(panel, /\{!pending && derived\.kind === "ok" && \(/);
});

test("情境輸入控制皆為 44px 觸控熱區、control 圓角 rounded-lg（設計系統 §4.2／§7）", () => {
  assert.match(panel, /const selectCls =\s*\n?\s*"min-h-11 rounded-lg/);
  const selects = panel.match(/<select/g) ?? [];
  const classed = panel.match(/className={selectCls}/g) ?? [];
  assert.equal(selects.length, classed.length, "每個 select 都必須套用 canonical control 樣式");
  assert.equal(selects.length, 6, "情境五軸＋主客分數共六個控制");
});

test("中文說明不得跨行寫在 JSX 文字節點（會渲染出多餘空白）", () => {
  // JSX 會把換行＋縮排壓成一個空格，中文句中因此出現空隙（2026-07-25 實測於
  // 「不符直覺的 排序」）。跨行中文一律以字串連接寫。
  const code = panel
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "") // JSX 註解（可跨行）
    .split("\n")
    .filter((line) => !line.trim().startsWith("//") && !line.trim().startsWith("*"))
    .join("\n");
  // 需含全形標點（U+FF01–FF60）：斷行常落在「，」「；」之後，只比對漢字會漏掉。
  const cjk = "[\\u4e00-\\u9fff\\u3000-\\u303f\\uff01-\\uff60]";
  const offender = code.match(new RegExp(`${cjk}[ \\t]*\\n[ \\t]*${cjk}`));
  assert.equal(offender, null, `跨行中文文字節點需改為字串連接：${offender?.[0] ?? ""}`);
});

test("色彩全走語意 token，零硬編 hex（設計系統 §2.8）", () => {
  assert.doesNotMatch(panel, /#[0-9a-fA-F]{3,8}\b/);
  assert.doesNotMatch(panel, /\b(?:text|bg|border)-(?:red|blue|green|amber|slate|gray)-\d{2,3}\b/);
});

test("必要文字不得用 text-faint（對比僅 2.6:1，設計系統 §2.1）", () => {
  // 本面板每一段文字都承載語意（機率區間、樣本數、模型限制與紅線揭露），
  // 因此全檔不得出現 text-faint；bg-faint 作為中性色塊仍可用。
  assert.ok(!panel.includes("text-faint"), "面板文字最低層級為 muted");
  assert.ok(panel.includes("bg-faint"), "出局組色塊仍走中性灰");
});
