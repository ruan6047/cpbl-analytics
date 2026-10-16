import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { HighlightsList } from "./series-highlights.tsx";
import { SeriesSummaryBlock } from "./series-summary.tsx";
import { mergeNotes, PAGE_NOTES } from "@/lib/playoffs-notes";
import {
  HIGHLIGHTS_NOTE,
  acceptHighlights,
  highlightsKey,
  highlightsPath,
  highlightsRows,
  type HighlightsPayload,
  type HighlightsState,
} from "@/lib/playoffs-series-highlights";
import { seriesSummaryNotes, type SeriesSummary } from "@/lib/playoffs-series-summary";

// 真實樣本：E1 的焦點規則欄位投影與黃金標籤（game-highlights.test.ts 同一份）；E2 合成「資料未到」、E3 合成「0 個標籤」。
const GOLD = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/game-highlights_2026E.json", import.meta.url), "utf8"));
const SUMMARY = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-series-summary_2026-10-16-g3.json", import.meta.url), "utf8")) as SeriesSummary;
const key = (sno: number) => ({ year: 2026, kind_code: "E" as const, game_sno: sno });
const PAYLOAD: HighlightsPayload = {
  contract: "playoffs-highlights/v1", context_version: "cv1", series: "E", status: "ok",
  games: [
    { series_game_no: 1, game_key: key(1), data_status: "ok", input: GOLD.input },
    { series_game_no: 2, game_key: key(2), data_status: "pending", input: null },
    { series_game_no: 3, game_key: key(3), data_status: "ok",
      input: { game: GOLD.input.game, scoreboard: [], livelog: [], batting: [], pitching: [], decisions: {} } },
  ],
};
const router = { back() {}, forward() {}, refresh() {}, push() {}, replace() {}, prefetch() {} };
const html = (node: ReactElement) => render(<AppRouterContext.Provider value={router as never}>{node}</AppRouterContext.Provider>);
const text = (s: string) => s.replace(/<[^>]+>/g, "");

test("列模型：ok 跑單場頁同一函式（＝黃金值）、pending 不算、0 個標籤；連結到單場頁", () => {
  const rows = highlightsRows(PAYLOAD);
  assert.deepEqual(rows.map((r) => [r.label, r.status, r.href]), [
    ["G1", "ok", "/games/1?kind=E&year=2026"], ["G2", "pending", "/games/2?kind=E&year=2026"],
    ["G3", "ok", "/games/3?kind=E&year=2026"]]);
  assert.deepEqual(rows[0].tags, GOLD.expected.E1);
  assert.deepEqual(rows[1].tags, []);
  assert.deepEqual(rows[2].tags, []);
});

test("格內：有標籤列標籤、資料未到「待更新」、0 個「—」；整列可點、44px", () => {
  const out = html(<HighlightsList state={{ kind: "data", data: PAYLOAD }} kind="E" />);
  const t = text(out);
  for (const h of GOLD.expected.E1) assert.ok(t.includes(h.text), h.text);
  assert.ok(t.includes("G2待更新") && t.includes("G3—"));
  assert.equal((out.match(/<a [^>]*href="\/games\/\d\?kind=E&amp;year=2026"/g) ?? []).length, 3);
  for (const a of out.match(/<a [^>]*>/g) ?? []) assert.match(a, /min-h-11/);
  assert.match(out, /class="pm-tag inline-flex/);           // 沿用單場頁本場焦點 Chip 樣式
});

test("狀態：載入前只留占位（無「待更新」閃爍）；讀取失敗且無上一份 ⇒ 整段「待更新」", () => {
  const idle = html(<HighlightsList state={{ kind: "idle" }} kind="E" />);
  assert.match(idle, /aria-busy="true"/);
  assert.doesNotMatch(text(idle), /待更新|—/);
  assert.equal(text(html(<HighlightsList state={{ kind: "failed", previous: null }} kind="E" />)), "待更新");
  const empty = { ...PAYLOAD, status: "no_completed_games" as const, games: [] };
  assert.equal(text(html(<HighlightsList state={{ kind: "data", data: empty }} kind="E" />)), "—");
});

test("版本：相同才採用；不同 ⇒ 保留上一份（不拼接）；沒有上一份 ⇒ failed；失敗回應同樣保留", () => {
  const idle: HighlightsState = { kind: "idle" };
  assert.deepEqual(acceptHighlights(idle, PAYLOAD, "cv1"), { kind: "data", data: PAYLOAD });
  assert.deepEqual(acceptHighlights(idle, PAYLOAD, "cv2"), { kind: "failed", previous: null });
  const had: HighlightsState = { kind: "data", data: PAYLOAD };
  const newer = { ...PAYLOAD, context_version: "cv9", games: [] };
  assert.deepEqual(acceptHighlights(had, newer, "cv1"), had);            // 回應版本與畫面不同 ⇒ 丟棄
  assert.deepEqual(acceptHighlights(had, null, "cv1"), had);             // 讀取失敗 ⇒ 保留上一份
  assert.deepEqual(acceptHighlights(had, newer, "cv9"), { kind: "data", data: newer });
  assert.deepEqual(acceptHighlights(idle, PAYLOAD, null), { kind: "failed", previous: null });
});

test("重抓鍵：版本、場數、涵蓋、PA build 任一改變才變；路徑", () => {
  const b = SUMMARY.previous!;
  const k0 = highlightsKey("cv1", b);
  assert.equal(highlightsKey("cv1", structuredClone(b)), k0);
  assert.notEqual(highlightsKey("cv2", b), k0);
  assert.notEqual(highlightsKey("cv1", { ...b, games_covered: b.games_covered - 1 }), k0);
  assert.notEqual(highlightsKey("cv1", { ...b, source: { ...b.source, pa_build_ids_hash: "x" } }), k0);
  assert.equal(highlightsPath(2026, "C"), "/api/v1/playoffs/highlights?season=2026&series=C");
});

test("掛載：新版 summary（帶 year／context_version）才出逐場焦點；舊版不出、也不出頁尾", () => {
  const withK3 = { ...structuredClone(SUMMARY), year: 2026, context_version: "cv1" };
  const out = html(<SeriesSummaryBlock summary={withK3} />);
  assert.match(out, /data-highlights-block="E"/);
  assert.match(out, /三大轉折[\s\S]*逐場焦點/);                        // 放在三大轉折之後
  assert.doesNotMatch(html(<SeriesSummaryBlock summary={SUMMARY} />), /data-highlights-block/);
  assert.ok(seriesSummaryNotes({ series_summary: withK3 }).some((n) => n.key === HIGHLIGHTS_NOTE.key));
  assert.ok(!seriesSummaryNotes({ series_summary: SUMMARY }).some((n) => n.key === HIGHLIGHTS_NOTE.key));
});

test("頁尾：固定一條、≤80 字、與既有條目合併無衝突", () => {
  const withK3 = { ...structuredClone(SUMMARY), year: 2026, context_version: "cv1" };
  const { notes, conflicts } = mergeNotes([{ area: "series", notes: [...PAGE_NOTES.series, ...seriesSummaryNotes({ series_summary: withK3 })] }]);
  assert.deepEqual(conflicts, []);
  assert.equal(notes.filter((n) => n.key === "series.highlights_method").length, 1);
  assert.ok([...HIGHLIGHTS_NOTE.text].length <= 80);
});
