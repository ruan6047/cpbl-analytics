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
