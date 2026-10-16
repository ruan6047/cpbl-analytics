import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup as render } from "react-dom/server";

import { AreaFrame, isPlaceholder, takeFirstContent, type AnchorStates } from "./area-frame.tsx";

// #285 批次 B WP-F2（發現 2）：最小高度只在占位（區元件未掛上）時套用；掛上後外框高＝元件高。
// 以及錨點補正（需求方「錨點位移：甲」）的判斷函式；DOM 行為由本機真實瀏覽器取證（exec-3/anchor.json）。

type Fake = { context_version: string; label: string };
const S = ({ data }: { data: Fake | null }) => <section><p>{data ? data.label : "讀取失敗"}</p></section>;
const prev = { context_version: "v1", label: "上一份" };
const frame = (state: Parameters<typeof AreaFrame<Fake>>[0]["state"]) =>
  render(<AreaFrame id="roster" state={state} Section={S} minHeightPx={480} />);
/** 以 AreaFrame 真實輸出的第一個子節點判斷「已有內容」（與瀏覽器端 anchorStates 同一規則）。 */
const FrameState = (state: Parameters<typeof AreaFrame<Fake>>[0]["state"]): boolean => {
  const m = /^<div id="roster"[^>]*><([a-z]+)([^>]*)>/.exec(frame(state))!;
  const role = /role="([^"]+)"/.exec(m[2])?.[1] ?? null;
  return !isPlaceholder({ tagName: m[1].toUpperCase(), getAttribute: (n) => (n === "role" ? role : null) });
};
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
  // 掛載當下：全部占位
  assert.deepEqual(step([["watch", false], ["roster", false], ["teams", false]]), { realign: false, settled: false });
  // 目標 teams 先到（比較區先回）
  assert.deepEqual(step([["watch", false], ["roster", false], ["teams", true]]), { realign: true, settled: false });
  // 前面的 roster 晚到（名單缺使外框變矮／名單齊使外框變高）⇒ 再對齊一次
  assert.deepEqual(step([["watch", false], ["roster", true], ["teams", true]]), { realign: true, settled: false });
  // 第 4 區最後到 ⇒ 再對齊，並且全部到齊
  assert.deepEqual(step([["watch", true], ["roster", true], ["teams", true]]), { realign: true, settled: true });
  // 之後輪詢（stale／error 有上一份仍是內容）都不再對齊
  assert.deepEqual(step([["watch", true], ["roster", true], ["teams", true]]), { realign: false, settled: true });
});

test("審核 B-01：首輪錯版的 stale 占位（沒有上一份）不算第一次內容；下一輪真正取得時仍重新對齊", () => {
  const seen = new Set<string>();
  const S = FrameState;
  // 首輪：roster stale 無上一份（占位）、teams 與 watch 已有內容
  const r1 = takeFirstContent([["watch", S({ kind: "data", data: prev })], ["roster", S({ kind: "stale", previous: null })],
    ["teams", S({ kind: "data", data: prev })]], seen);
  assert.deepEqual(r1, { realign: true, settled: false });          // 未齊：觀察器 ⛔ 斷開
  // 下一輪：roster 真正取得 ⇒ 重新對齊
  const r2 = takeFirstContent([["watch", true], ["roster", S({ kind: "data", data: prev })], ["teams", true]], seen);
  assert.deepEqual(r2, { realign: true, settled: true });
});

test("isPlaceholder 與 AreaFrame 實際輸出一致：idle／stale 無上一份是占位；data／error／stale 有上一份不是", () => {
  for (const [st, want] of [
    [{ kind: "idle" }, true], [{ kind: "stale", previous: null }, true],
    [{ kind: "data", data: prev }, false], [{ kind: "error", previous: null }, false],
    [{ kind: "error", previous: prev }, false], [{ kind: "stale", previous: prev }, false],
  ] as const) assert.equal(FrameState(st), !want, st.kind);
});

test("第 4 區外框（watch-area）的占位也是 p role=status：idle、stale 無上一份", async () => {
  const { WatchArea } = await import("./watch-area.tsx");
  for (const state of [{ kind: "idle" }, { kind: "stale", previous: null }] as const) {
    const out = render(<WatchArea state={state} overview={null} requested={false} />);
    assert.match(out, /^<div id="watch"[^>]*><p role="status"/, state.kind);
  }
});
