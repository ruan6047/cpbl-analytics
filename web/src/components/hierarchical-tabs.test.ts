import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./hierarchical-tabs.tsx", import.meta.url), "utf8");

test("階層導覽四種控制的觸控目標皆至少 44px", () => {
  const targets = source.match(/className={`min-h-11/g) ?? [];
  assert.equal(targets.length, 3, "母層分段、頁籤（MainTabs，也是階層導覽的子層）與情境切換都應使用 min-h-11");
  assert.doesNotMatch(source, /className={`min-h-(?:8|9|10)\b/);
});

// #220 第三輪：依核可稿 player.html「範圍列 → 頁籤帶 → tabpanel」。父層＝範圍列分段（aria-pressed），
// 子層＝頁籤帶且為導覽最後一列（帶直接接呼叫端的 TabPanel）；情境 controls 在範圍列，不在帶與面板之間。
test("階層導覽：父層分段與 controls 在上，子層頁籤帶在最後一列", async () => {
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { HierarchicalTabs } = await import("./hierarchical-tabs.tsx");
  const html = renderToStaticMarkup(createElement(HierarchicalTabs, {
    label: "資料範圍",
    groups: [
      { value: "season", label: "本季", items: [{ value: "ov", label: "總覽" }, { value: "tr", label: "逐球追蹤" }] },
      { value: "career", label: "生涯", items: [{ value: "ov", label: "總覽" }] },
    ],
    activeGroup: "season", activeItem: "ov",
    onGroupChange: () => {}, onItemChange: () => {},
    controls: createElement("span", { id: "ctl" }, "層級"),
  }));
  const group = html.indexOf('role="group" aria-label="資料範圍"');
  const ctl = html.indexOf('id="ctl"');
  const tablist = html.indexOf('role="tablist"');
  assert.ok(group >= 0 && ctl > group && tablist > ctl, "順序須為 父層分段 → controls → 子層頁籤帶");
  const band = html.slice(tablist);
  assert.match(band, /role="tab"[^>]*>總覽</);
  assert.match(band, /role="tab"[^>]*>逐球追蹤</);
  assert.doesNotMatch(band, />(?:本季|生涯)<|id="ctl"/, "頁籤帶之後不得再有父層按鈕或 controls");
  assert.doesNotMatch(html.slice(0, tablist), /role="tab"/, "父層是 aria-pressed 分段，不是 tab");
  assert.match(html.slice(group, tablist), /aria-pressed="true"[^]*本季/);
});
