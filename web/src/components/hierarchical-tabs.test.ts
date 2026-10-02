import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./hierarchical-tabs.tsx", import.meta.url), "utf8");

test("階層導覽四種控制的觸控目標皆至少 44px", () => {
  const targets = source.match(/className={`min-h-11/g) ?? [];
  assert.equal(targets.length, 3, "母層分段、頁籤（MainTabs，也是階層導覽的子層）與情境切換都應使用 min-h-11");
  assert.doesNotMatch(source, /className={`min-h-(?:8|9|10)\b/);
});

// #220 需求方裁定（issuecomment-5945865835）：恢復正式版同列排列——
// 作用中父層 → 其子頁籤 → 其他父層 → 右側 controls，全在同一個 `.pm-navrow` 列容器內。
// 父層位置固定（不因作用中而移到最前），子頁籤緊接作用中父層；父層 aria-pressed、子層 tab 語意分離。
async function renderNav(activeGroup: "season" | "career") {
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { HierarchicalTabs } = await import("./hierarchical-tabs.tsx");
  return renderToStaticMarkup(createElement(HierarchicalTabs, {
    label: "資料範圍",
    groups: [
      { value: "season", label: "本季", items: [{ value: "ov", label: "總覽" }, { value: "tr", label: "逐球追蹤" }] },
      { value: "career", label: "生涯", items: [{ value: "cov", label: "生涯總覽" }] },
    ],
    activeGroup, activeItem: activeGroup === "season" ? "ov" : "cov",
    onGroupChange: () => {}, onItemChange: () => {},
    controls: createElement("span", { id: "ctl" }, "層級"),
  }));
}

test("階層導覽：父層、子頁籤與 controls 同一列，子頁籤緊接作用中父層", async () => {
  const html = await renderNav("season");
  assert.equal(html.match(/class="pm-navrow"/g)?.length, 1, "整個導覽只有一個列容器");
  assert.doesNotMatch(html, /pm-scope/, "不得再有帶上方的範圍列");
  const order = [/aria-pressed="true"[^>]*>本季</, /role="tab"[^>]*>總覽</, /role="tab"[^>]*>逐球追蹤</,
    /aria-pressed="false"[^>]*>生涯</, /id="ctl"/].map((re) => html.search(re));
  assert.ok(order.every((at, i) => at >= 0 && (i === 0 || at > order[i - 1])),
    `順序須為 本季 → 本季子頁籤 → 生涯 → controls：${order.join(",")}`);
  assert.match(html, /class="pm-navrow-ctl"><span id="ctl"/, "controls 在列內右側插槽");
  assert.doesNotMatch(html, /aria-pressed[^>]*role="tab"|role="tab"[^>]*aria-pressed/, "父層不是 tab");
});

test("階層導覽：切到第二個父層時父層位置不變、子頁籤改接在它後面", async () => {
  const html = await renderNav("career");
  const order = [/aria-pressed="false"[^>]*>本季</, /aria-pressed="true"[^>]*>生涯</, /role="tab"[^>]*>生涯總覽</,
    /id="ctl"/].map((re) => html.search(re));
  assert.ok(order.every((at, i) => at >= 0 && (i === 0 || at > order[i - 1])), `順序：${order.join(",")}`);
  assert.doesNotMatch(html, />逐球追蹤</, "只顯示作用中父層的子頁籤");
});

// #220 需求方裁定（issuecomment-5946305065）：窄螢幕視覺順序須等於鍵盤焦點（DOM）順序。
// controls 在 DOM 中排在頁籤帶之後，CSS 若以 `order` 把它挪到帶上方，焦點就會與畫面相反。
test("同列導覽：.pm-navrow 各規則不得以 order 重排（視覺順序＝焦點順序）", () => {
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  const rules = [...css.matchAll(/\.pm-navrow[\w-]*\s*\{[^}]*\}/g)].map((m) => m[0]);
  assert.ok(rules.length >= 4, "找得到 .pm-navrow 規則");
  for (const rule of rules) assert.doesNotMatch(rule, /(^|[\s;{])order\s*:/, rule);
});

// 球隊頁年度／半季須回到同列導覽（正式版行為），不放進內容面板。
test("球隊頁：半季為賽季子頁籤、年度為同列右側 controls", () => {
  const team = readFileSync(new URL("../app/teams/[code]/team-tabs.tsx", import.meta.url), "utf8");
  assert.match(team, /<HierarchicalTabs\b/);
  assert.match(team, /items: g\.value === SEASON_GROUP \? seasonItems/, "半季是賽季群組的子頁籤");
  assert.match(team, /controls=\{onSeason && years\.length > 1\s*\?\s*<YearSelect/);
  assert.doesNotMatch(team, /ContextSwitcher/, "半季不再是面板內的分段切換");
});
