import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Postmark } from "./postmark.tsx";

// #220 F1：郵戳戳面 aria-hidden，常是該處日期／球場的唯一出處。判準落在
// 「輔助科技讀得到的字」：先剔除 aria-hidden 子樹，再看剩下的文字。

/** 剔除 aria-hidden="true" 的元素（含子樹）後的可讀文字。 */
function accessibleText(node: ReactElement): string {
  const html = renderToStaticMarkup(node);
  // 逐個 token 走：進入 aria-hidden 元素後記深度，深度歸零前的文字一律略過。
  let hiddenDepth = 0;
  const parts: string[] = [];
  for (const m of html.matchAll(/<(\/?)(\w+)([^>]*)>|([^<]+)/g)) {
    const [, closing, , attrs, textPart] = m;
    if (textPart !== undefined) {
      if (hiddenDepth === 0) parts.push(textPart);
    } else if (closing) {
      if (hiddenDepth > 0) hiddenDepth -= 1;
    } else if (!attrs.endsWith("/")) {
      if (hiddenDepth > 0 || /aria-hidden="true"/.test(attrs)) hiddenDepth += 1;
    }
  }
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

test("郵戳預設把完整日期與球場交給輔助科技（賽況頁頂）", () => {
  const text = accessibleText(<Postmark date="2026-09-28" venue="洲際" size="sm" />);
  assert.equal(text, "2026年9月28日，球場 洲際");
});

test("announce=venue 只補球場，不重複區塊標題已說過的日期（首頁今日票券）", () => {
  const text = accessibleText(<Postmark date="2026-10-02" venue="新莊" placed="absolute" announce="venue" />);
  assert.equal(text, "球場 新莊");
});

test("缺球場：預設只說日期；只說球場的模式什麼都不輸出，不造字", () => {
  assert.equal(accessibleText(<Postmark date="2026-09-28" venue={null} />), "2026年9月28日");
  assert.equal(accessibleText(<Postmark date="2026-09-28" venue={null} announce="venue" />), "");
});

test("戳面本身仍對輔助科技隱藏（不與替代文字重複朗讀）", () => {
  const html = renderToStaticMarkup(<Postmark date="2026-09-28" venue="洲際" />);
  assert.match(html, /<span class="pm-post[^"]*"[^>]*aria-hidden="true">/);
});
