import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup as render } from "react-dom/server";

import { AreaFrame } from "./area-frame.tsx";

// #285 批次 B WP-F2（發現 2）：最小高度只在占位（區元件未掛上）時套用；掛上後外框高＝元件高。

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
