import assert from "node:assert/strict";
import test from "node:test";

import { PAGE_NOTES, isAllowedSourceUrl, mergeNotes, shownData, staticNoteConflicts, type PlayoffsNote } from "./playoffs-notes.ts";
import { PLAYOFFS_AREA_ORDER } from "./playoffs-areas.ts";

// #285 續做 WP2：全頁頁尾說明的合併規則（MOUNT-CONTRACT r3 §2.4、§2.5）。

const n = (key: string, text = key): PlayoffsNote => ({ key, text });

test("依 C2 區序排列（與輸入順序無關），同區內照回傳順序", () => {
  const { notes } = mergeNotes([
    { area: "teams", notes: [n("teams.a"), n("teams.b")] },
    { area: "roster", notes: [n("roster.a")] },
    { area: "series", notes: [n("series.a")] },
    { area: "watch", notes: [n("watch.a")] },
  ]);
  assert.deepEqual(notes.map((x) => x.key), ["series.a", "watch.a", "roster.a", "teams.a", "teams.b"]);
  assert.deepEqual([...PLAYOFFS_AREA_ORDER], ["series", "watch", "roster", "teams"]);
});

test("同 key 只出現一次、位置取第一次；common.* 跟在第一次出現處", () => {
  const { notes, conflicts } = mergeNotes([
    { area: "teams", notes: [n("common.source", "同一句"), n("teams.x")] },
    { area: "roster", notes: [n("roster.y"), n("common.source", "同一句")] },
  ]);
  assert.deepEqual(notes.map((x) => x.key), ["roster.y", "common.source", "teams.x"]);
  assert.deepEqual(conflicts, []);
});

test("同 key 不同文字：取第一條並回報衝突", () => {
  const { notes, conflicts } = mergeNotes([
    { area: "roster", notes: [n("common.k", "第一條")] },
    { area: "teams", notes: [n("common.k", "第二條")] },
  ]);
  assert.deepEqual(notes, [n("common.k", "第一條")]);
  assert.deepEqual(conflicts, [{ key: "common.k", kept: "第一條", dropped: "第二條" }]);
});

test("同一 key 隨資料改文字時位置不變", () => {
  const round = (missing: string) => mergeNotes([
    { area: "teams", notes: [n("teams.fixed"), n("teams.series_pending_source", `本系列第 ${missing} 場的 box 尚未送達`), n("teams.tail")] },
  ]).notes;
  const a = round("2"), b = round("2、3");
  assert.deepEqual(a.map((x) => x.key), b.map((x) => x.key));
  assert.notEqual(a[1].text, b[1].text);
});

test("0 條 ⇒ 空結果（頁尾整區不渲染由元件測試負責）；G1 前 PAGE_NOTES 為空", () => {
  assert.deepEqual(mergeNotes([]).notes, []);
  assert.deepEqual(PAGE_NOTES, { series: [], watch: [] });
});

test("畫面上那份資料：data＝新資料；stale／error＝上一份；未載入或無上一份＝null（⛔ 用被拒回應）", () => {
  assert.equal(shownData(undefined), null);
  assert.equal(shownData({ kind: "idle" }), null);
  assert.deepEqual(shownData({ kind: "data", data: { v: 2 } }), { v: 2 });
  assert.deepEqual(shownData({ kind: "stale", previous: { v: 1 } }), { v: 1 });
  assert.deepEqual(shownData({ kind: "error", previous: { v: 1 } }), { v: 1 });
  assert.equal(shownData({ kind: "error", previous: null }), null);
});

test("來源連結只收站內相對路徑或官方站 https", () => {
  for (const ok of ["/methodology#pregame", "https://www.cpbl.com.tw/xmdoc/cont?SId=1", "https://stats.cpbl.com.tw/x"]) assert.equal(isAllowedSourceUrl(ok), true, ok);
  for (const bad of ["//evil.com/x", "http://www.cpbl.com.tw/", "https://evil.com/", "javascript:alert(1)", "ftp://cpbl.com.tw"]) assert.equal(isAllowedSourceUrl(bad), false, bad);
});

test("審核 F2：以正規化後結果判斷站內，反斜線、空白、控制字元與帳密寫法都拒收", () => {
  const bad = [
    "/\\example.com/receipt",          // 正斜線＋反斜線：瀏覽器解析成 //example.com
    "/\t/example.com/receipt",          // Tab 被移除後成 //example.com
    "/\n/example.com/receipt",
    "/\r/example.com/receipt",
    "/ /example.com",
    "\\\\example.com/x",
    "/\u0000/example.com",
    "https://www.cpbl.com.tw\\@evil.com/",
    "https://www.cpbl.com.tw@evil.com/",
    "https://user:pw@www.cpbl.com.tw/",
  ];
  for (const url of bad) assert.equal(isAllowedSourceUrl(url), false, JSON.stringify(url));
  const base = "https://site.example";
  const good = ["/methodology#pregame", "/games/1?kind=C&year=2026", "/%5Cexample.com", "https://www.cpbl.com.tw/xmdoc/cont?SId=1"];
  for (const url of good) {
    assert.equal(isAllowedSourceUrl(url), true, url);
    if (url.startsWith("/")) assert.equal(new URL(url, base).origin, base, url);   // 放行者解析後確為站內
  }
});

test("固定說明 key 一致性：已登記區 notes(null)＋PAGE_NOTES 同 key 文字必須相同", async () => {
  const { PLAYOFFS_AREAS } = await import("../components/playoffs/area-registry.ts");
  const groups = [
    { area: "series" as const, notes: PAGE_NOTES.series },
    { area: "watch" as const, notes: PAGE_NOTES.watch },
    ...PLAYOFFS_AREAS.map((r) => ({ area: r.id, notes: r.notes ? r.notes(null) : [] })),
  ];
  assert.deepEqual(staticNoteConflicts(groups), []);
  // 檢查本身會抓到衝突（避免空集合永遠通過）
  assert.equal(staticNoteConflicts([{ area: "roster", notes: [n("common.a", "x")] }, { area: "teams", notes: [n("common.a", "y")] }]).length, 1);
});
