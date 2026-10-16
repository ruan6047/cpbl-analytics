import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup as render } from "react-dom/server";

import { AreaFrame, takeFirstContent, type AnchorStates } from "./area-frame.tsx";

// #285 批次 B WP-F2（發現 2）：最小高度只在占位（區元件未掛上）時套用；掛上後外框高＝元件高。
// 以及錨點補正（需求方「錨點位移：甲」）的判斷函式；DOM 行為由本機真實瀏覽器取證（exec-3/anchor.json）。

type Fake = { context_version: string; label: string };
const S = ({ data }: { data: Fake | null }) => <section><p>{data ? data.label : "讀取失敗"}</p></section>;
const prev = { context_version: "v1", label: "上一份" };
const frame = (state: Parameters<typeof AreaFrame<Fake>>[0]["state"]) =>
  render(<AreaFrame id="roster" state={state} Section={S} minHeightPx={480} />);
const hasMin = (s: string) => /^<div id="roster"[^>]*style="min-height:480px"/.test(s);

test("idle、stale 無上一份 ⇒ 有占位最小高度", () => {
  assert.ok(hasMin(frame({ kind: "idle" })));
  assert.ok(hasMin(frame({ kind: "stale", previous: null })));
});

test("data、error（有無上一份）、stale 有上一份 ⇒ 無最小高度", () => {
  for (const st of [
    { kind: "data", data: { context_version: "v2", label: "新" } },
    { kind: "error", previous: prev },
    { kind: "error", previous: null },
    { kind: "stale", previous: prev },
  ] as const) {
    const out = frame(st);
    assert.ok(!/min-height/.test(out.slice(0, out.indexOf(">"))), `${st.kind}: ${out.slice(0, 120)}`);
  }
});

test("未給 minHeightPx 時占位用預設高度", () => {
  const out = render(<AreaFrame id="teams" state={{ kind: "idle" }} Section={S} />);
  assert.match(out, /^<div id="teams"[^>]*style="min-height:\d+px"/);
});

// #285 批次 B 錨點補正（需求方「錨點位移：甲」）：目標區或它前面任一區第一次取得內容 ⇒ 重新對齊；之後不再。

test("錨點補正：前面的區或目標區第一次取得內容才重新對齊，輪詢更新與 stale／error 轉換不對齊", () => {
  const seen = new Set<string>();
  const step = (s: AnchorStates) => takeFirstContent(s, seen);
  // 掛載當下：全部 idle
  assert.deepEqual(step([["watch", "idle"], ["roster", "idle"], ["teams", "idle"]]), { realign: false, settled: false });
  // 目標 teams 先到（比較區先回）
  assert.deepEqual(step([["watch", "idle"], ["roster", "idle"], ["teams", "data"]]), { realign: true, settled: false });
  // 前面的 roster 晚到（名單缺使外框變矮／名單齊使外框變高）⇒ 再對齊一次
  assert.deepEqual(step([["watch", "idle"], ["roster", "data"], ["teams", "data"]]), { realign: true, settled: false });
  // 第 4 區最後到 ⇒ 再對齊，並且全部到齊
  assert.deepEqual(step([["watch", "data"], ["roster", "data"], ["teams", "data"]]), { realign: true, settled: true });
  // 之後輪詢：stale／error／data 互轉都不再對齊
  assert.deepEqual(step([["watch", "stale"], ["roster", "error"], ["teams", "data"]]), { realign: false, settled: true });
});

test("錨點補正：第一次就是 error 也算取得內容；外框後方的區不在判斷範圍（由呼叫端只傳目標之前者）", () => {
  const seen = new Set<string>();
  assert.equal(takeFirstContent([["watch", "error"], ["roster", "idle"]], seen).realign, true);
  assert.equal(takeFirstContent([["watch", "error"], ["roster", "idle"]], seen).realign, false);
  assert.equal(takeFirstContent([["watch", "error"], ["roster", "stale"]], seen).realign, true);
});
