import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { SeriesSummaryBlock } from "./series-summary.tsx";
import { PageNotes } from "./page-notes.tsx";
import { isAllowedSourceUrl, mergeNotes, PAGE_NOTES } from "@/lib/playoffs-notes";
import { seriesSummaryNotes, taipeiShort, type SeriesAwards, type SeriesSummary } from "@/lib/playoffs-series-summary";

// 真實樣本（WP-G3 版 series_summary，獎項 pending_source）＋合成的獎項狀態（官方系列獎項尚未公布）。
const REAL = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-series-summary_2026-10-16-g3.json", import.meta.url), "utf8")) as SeriesSummary;
const URL_ = "https://www.cpbl.com.tw/news/view?id=999";
const withAwards = (aw: SeriesAwards): SeriesSummary => {
  const s = structuredClone(REAL);
  s.previous!.awards = aw;
  return s;
};
const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const text = (s: string) => s.replace(/<[^>]+>/g, "");
const notes = (s: SeriesSummary) => seriesSummaryNotes({ series_summary: s });

const PUBLISHED: SeriesAwards = {
  status: "published", revision: 2, source_url: URL_, checked_at: "2026-10-26T13:05:00+00:00",
  awards: [
    { award_name: "測試挑戰賽最有價值球員", award_type: "series_mvp", winners: [
      { player_id: "0000004636", name: "甲一", team_code: "ACN011" },
      { player_id: null, name: "乙二", team_code: null }] },
    { award_name: "測試其他獎", award_type: "other", winners: [{ player_id: null, name: "丙三", team_code: "ADD011" }] },
  ],
};

test("本站尚未取得（含表未建）：格內「待更新」、頁尾 awards_pending（G2 行為不變）", () => {
  const t = text(html(<SeriesSummaryBlock summary={REAL} />));
  assert.ok(t.includes("官方系列獎項待更新"));
  const n = notes(REAL);
  assert.ok(n.some((x) => x.key === "series.awards_pending"));
  assert.ok(!n.some((x) => x.key.startsWith("series.awards_not_published") || x.key.startsWith("series.awards_source")));
});

test("官方尚未公布：格內「待更新」、頁尾寫查核時間（台北），與未取得分開", () => {
  const s = withAwards({ status: "not_published", revision: 1, source_url: URL_, checked_at: "2026-10-26T13:05:00+00:00" });
  assert.ok(text(html(<SeriesSummaryBlock summary={s} />)).includes("官方系列獎項待更新"));
  const n = notes(s);
  const np = n.find((x) => x.key === "series.awards_not_published.E")!;
  assert.equal(np.text, "季後挑戰賽官方尚未公布本系列獎項（本站 10/26 21:05 查核）。");
  assert.ok(!n.some((x) => x.key === "series.awards_pending"));   // 這系列不是「未取得」
});

test("已公布：官方完整名稱＋全部得主依序（共同得主不壓成一人），頁尾附官方來源連結", () => {
  const s = withAwards(PUBLISHED);
  const out = html(<SeriesSummaryBlock summary={s} />);
  const t = text(out);
  assert.match(out, /data-awards="published"/);
  assert.ok(t.includes("測試挑戰賽最有價值球員甲一乙二測試其他獎丙三"));
  assert.ok(!t.includes("官方系列獎項待更新"));
  const src = notes(s).find((x) => x.key === "series.awards_source.E")!;
  assert.equal(src.text, "季後挑戰賽系列獎項依官方公布（本站 10/26 21:05 查核）。");
  assert.deepEqual(src.source, { label: "官方公布頁", url: URL_ });
  assert.ok(isAllowedSourceUrl(src.source!.url));
  const footer = html(<PageNotes notes={[src]} />);
  assert.match(footer, new RegExp(`<a href="${URL_.replace(/[?.]/g, "\\$&")}"[^>]*>官方公布頁</a>`));
});

test("已公布但 RE24 第一或 MVP 次數不影響獎項格；不出現本站推選字樣", () => {
  const t = text(html(<SeriesSummaryBlock summary={withAwards(PUBLISHED)} />));
  assert.doesNotMatch(t, /本站推選|本站 MVP/);
});

test("E、C 各自狀態的頁尾 key 不撞、合併無衝突、每條 ≤80 字", () => {
  const s = withAwards(PUBLISHED);
  s.current = { ...structuredClone(s.previous!), kind_code: "C",
    awards: { status: "not_published", revision: 1, source_url: URL_, checked_at: "2026-10-20T01:00:00+00:00" } };
  const { notes: merged, conflicts } = mergeNotes([{ area: "series", notes: [...PAGE_NOTES.series, ...notes(s)] }]);
  assert.deepEqual(conflicts, []);
  assert.ok(merged.some((x) => x.key === "series.awards_source.E") && merged.some((x) => x.key === "series.awards_not_published.C"));
  for (const x of merged) assert.ok([...x.text].length <= 80, `${x.key} ${[...x.text].length} 字`);
});

test("taipeiShort：UTC→台北、壞輸入原樣", () => {
  assert.equal(taipeiShort("2026-10-26T16:30:00Z"), "10/27 00:30");
  assert.equal(taipeiShort("bad"), "bad");
});
