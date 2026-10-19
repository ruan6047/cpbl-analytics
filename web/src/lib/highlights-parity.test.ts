import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { dbHighlightInput, gameHighlightsSource, HIGHLIGHTS_READY_TABLES } from "./game-highlights-source.ts";
import {
  checkSeriesParity, legacySingleGamePageHighlights, pageCompletedOf, singleGamePageHighlights,
} from "./highlights-parity.ts";
import type { HighlightInput } from "./game-highlights.ts";
import type { LiveApiResponse } from "./live-game.ts";
import type { HighlightsPayload } from "./playoffs-series-highlights.ts";

// #337 WP3：單場頁本場焦點 vs /playoffs 逐場焦點的機械檢查。
// 夾具＝正式站公開 API 真實回應（C2：已完賽、snapshot phase=final 仍在 48h 內、DB 四表到齊），見 _provenance。
// 「待更新」與 TTL 後兩種狀態由同一份真實回應只改單一欄位得到（正式站當下沒有該狀態的場次可取）。

const FX = JSON.parse(readFileSync(new URL("./__fixtures__/highlights-parity_2026-C2.json", import.meta.url), "utf8")) as {
  live: LiveApiResponse;
  playoffs: HighlightsPayload;
};
const live = () => structuredClone(FX.live);
const playoffs = () => structuredClone(FX.playoffs);
const lives = (raw: LiveApiResponse) => new Map([[2, raw]]);
const asInput = (raw: LiveApiResponse) => raw as unknown as HighlightInput;

// C2 賽後完整標籤（/playoffs 側，含失誤類；與 game-highlights-errors.test.ts 的批次 F 黃金值一致）。
const C2_FULL = [
  "梅賽鍶 連續解決 9 人［AAA011］",
  "呂彥青 連續解決 6 人［ACN011］",
  "曾聖安 道歉全壘打［AAA011］",
  "曾聖安 一棒逆轉［AAA011］",
  "兄弟 致命失誤（5 局）［ACN011］",
];

/** /playoffs 在 DB 未到齊時的形狀（series_highlights.py compute_payload：pending ⇒ input=None）。 */
const pendingPlayoffs = () => {
  const p = playoffs();
  p.games = p.games.map((g) => ({ ...g, data_status: "pending" as const, input: null }));
  return p;
};

test("正控（48h 內）：snapshot final 仍在時，單場頁焦點＝/playoffs 完整 5 標籤（含失誤類）", () => {
  const raw = live();
  assert.equal(raw.live_snapshot?.phase, "final");
  assert.equal(pageCompletedOf(raw), true);
  const r = checkSeriesParity(playoffs(), lives(raw));
  assert.equal(r.ok, true, JSON.stringify(r.games));
  assert.deepEqual(r.games.map((g) => [g.key, g.page.status, g.page.tags]), [["C-2", "ok", C2_FULL]]);
  assert.deepEqual(r.games[0].playoffs.tags, C2_FULL);
});

test("正控（TTL 後）：live_snapshot 為 null，單場頁焦點仍＝/playoffs 完整 5 標籤", () => {
  const raw = { ...live(), live_snapshot: null };
  const r = checkSeriesParity(playoffs(), lives(raw));
  assert.equal(r.ok, true, JSON.stringify(r.games));
  assert.deepEqual(r.games[0].page.tags, C2_FULL);
});

test("負控：換回修正前路徑 buildHighlights(applyLiveSnapshot(raw))，檢查必須判不一致（缺道歉全壘打與致命失誤）", () => {
  const r = checkSeriesParity(playoffs(), lives(live()), legacySingleGamePageHighlights);
  assert.equal(r.ok, false);
  const g = r.games[0];
  assert.equal(g.equal, false);
  assert.ok(!g.page.tags.includes("兄弟 致命失誤（5 局）［ACN011］"));
  assert.ok(!g.page.tags.includes("曾聖安 道歉全壘打［AAA011］"));
});

test("待更新：snapshot final、DB 任一表未到齊 ⇒ 單場頁不出標籤、與 /playoffs 同為待更新", () => {
  for (const t of HIGHLIGHTS_READY_TABLES) {
    const raw = { ...live(), [t]: [] } as LiveApiResponse;
    assert.equal(pageCompletedOf(raw), true, t);
    assert.deepEqual(singleGamePageHighlights(raw), { status: "pending", tags: [] }, t);
    const r = checkSeriesParity(pendingPlayoffs(), lives(raw));
    assert.equal(r.ok, true, `${t} ${JSON.stringify(r.games)}`);
    assert.equal(r.games[0].page.status, "pending");
    // 修正前路徑在這個窗口會出部分標籤 ⇒ 檢查必須判不一致（研究 E7(b)）
    assert.equal(checkSeriesParity(pendingPlayoffs(), lives(raw), legacySingleGamePageHighlights).ok, false, t);
  }
  assert.equal(dbHighlightInput(asInput({ ...live(), game: null })), null);
});

test("兩邊狀態不同就失敗：單場頁 ok 而 /playoffs 待更新、或找不到該場 /live 回應", () => {
  assert.equal(checkSeriesParity(pendingPlayoffs(), lives(live())).ok, false);
  const missing = checkSeriesParity(playoffs(), new Map());
  assert.equal(missing.ok, false);
  assert.equal(missing.games[0].page.status, "missing");
});

test("未完賽 ⇒ none（不顯示焦點，現行行為不變）；完賽判定只由呼叫端傳入", () => {
  assert.deepEqual(gameHighlightsSource(asInput(live()), false), { status: "none", tags: [] });
  assert.equal(gameHighlightsSource(asInput(live()), true).status, "ok");
});

test("到齊判準守衛：前端四表清單＝後端 series_highlights.py 的 ready 四表（兩處）", () => {
  const py = readFileSync(new URL("../../../src/cpbl/playoffs/series_highlights.py", import.meta.url), "utf8");
  const tuples = [...py.matchAll(/\(\s*("scoreboard"[^)]*)\)/g)]
    .map((m) => [...m[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]));
  assert.ok(tuples.length >= 2, `找不到後端 ready 四表清單：${tuples.length}`);
  for (const t of tuples) assert.deepEqual([...t].sort(), [...HIGHLIGHTS_READY_TABLES].sort());
  // game 列存在也是判準的一部分（compute_payload：game_row is not None）
  assert.match(py, /ready = game_row is not None and all\(tables\.values\(\)\)/);
});

test("單場頁接線守衛：焦點只走 gameHighlightsSource(覆蓋前 DB 列)，頁面不再直接呼叫 buildHighlights", () => {
  const page = readFileSync(new URL("../app/games/[sno]/game-live-page.tsx", import.meta.url), "utf8");
  assert.match(page, /gameHighlightsSource\(dbRows, completed\)/);
  assert.match(page, /setDbRows\(raw as unknown as Live\);\s*\n\s*const next = applyLiveSnapshot\(raw\);/);
  assert.doesNotMatch(page, /buildHighlights\(/);
});
