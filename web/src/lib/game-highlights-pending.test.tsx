import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { GameOverview } from "@/app/games/[sno]/overview";
import { TeamLines } from "@/app/games/[sno]/recap/team-lines";
import { HIGHLIGHTS_COPY } from "./playoffs-series-highlights.ts";

// #337 WP2：單場頁兩個焦點插槽（總覽、賽後 recap）在 DB 未到齊時顯示「待更新」，不出任何標籤；
// 字樣與 /playoffs 逐場焦點同一常數。合成輸入（只有呈現，無比賽事實）。

const TAG = { text: "虛構標籤", team: null };
const overview = (pending: boolean, highlights = [] as { text: string; team: string | null }[]) => renderToStaticMarkup(
  <GameOverview wp={[]} log={[]} homeName="主" awayName="客" homeColor="#000" awayColor="#000" onJump={() => {}}
    highlights={highlights} highlightsPending={pending} milestones={[]} info={[]} mvp={null} decisions={[]} />);
const recap = (pending: boolean, highlights = [] as { text: string; team: string | null }[]) => renderToStaticMarkup(
  <TeamLines highlights={highlights} highlightsPending={pending} milestones={[]} info={[]} />);

test("待更新：總覽與 recap 都在「本場焦點」下顯示 /playoffs 同一字樣", () => {
  assert.equal(HIGHLIGHTS_COPY.pending, "待更新");
  for (const html of [overview(true), recap(true)]) {
    assert.match(html, /本場焦點/);
    assert.match(html, /data-testid="highlights-pending"[^>]*>待更新</);
    assert.doesNotMatch(html, /pm-tag/);
  }
});

test("非待更新：有標籤照舊出 chip；無標籤且無其他內容時整塊不渲染（現行行為不變）", () => {
  for (const html of [overview(false, [TAG]), recap(false, [TAG])]) {
    assert.match(html, /虛構標籤/);
    assert.doesNotMatch(html, /highlights-pending/);
  }
  assert.equal(overview(false), "");
  assert.equal(recap(false), "");
});
