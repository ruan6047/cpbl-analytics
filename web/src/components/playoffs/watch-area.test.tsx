import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { WATCH_COPY, WatchArea } from "./watch-area.tsx";
import type { PlayoffsOverview } from "@/lib/playoffs-types";
import type { PlayoffsWatch } from "@/lib/playoffs-watch";

// 真實樣本：本機 API 唯讀抽取的 2026-10-15 overview／watch（各自 _provenance）；各態由它複製後改單一欄位。
const OV = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-overview_2026-10-15.json", import.meta.url), "utf8")) as PlayoffsOverview;
const W = JSON.parse(readFileSync(new URL("../../lib/__fixtures__/playoffs-watch_2026-10-15.json", import.meta.url), "utf8")) as PlayoffsWatch;
const html = (el: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(el);
const text = (s: string) => s.replace(/<[^>]+>/g, "");
/** WatchSection 必須是 #watch 的第一個子節點（輪詢換狀態時位置不變、不 remount）。 */
const sectionFirst = (s: string) => /^<div id="watch"[^>]*><section aria-labelledby="watch-heading"/.test(s);

test("data：#watch 掛整個 WatchSection（4B 兩格占位＋每隊先發灰列，E3／E1），不含 074 打序", () => {
  const out = html(<WatchArea state={{ kind: "data", data: W }} overview={OV} requested={false} />);
  assert.ok(sectionFirst(out));
  assert.equal((out.match(/data-slot="/g) ?? []).length, 0);
  assert.equal((text(out).match(/賽前快照尚未發布/g) ?? []).length, 0);
  assert.equal((out.match(/data-starter-status="unknown"/g) ?? []).length, 2);
  assert.equal((text(out).match(/官方先發投手：未知（來源尚未接入，S11）/g) ?? []).length, 2);
  assert.match(text(out), /觀戰重點/);
  assert.doesNotMatch(text(out), /打序|先發打線公告/);
  assert.doesNotMatch(text(out), /資料更新中|載入中/);
});

test("idle：首次取得前只有固定高度占位（min-h），不掛元件", () => {
  const out = html(<WatchArea state={{ kind: "idle" }} overview={OV} requested={false} />);
  assert.match(out, /<div id="watch" class="[^"]*min-h-48/);
  assert.match(text(out), new RegExp(WATCH_COPY.loading));
  assert.doesNotMatch(out, /watch-heading/);
});

test("stale：保留上一份一致畫面＋資料更新中，提示在元件之後；無上一份時只寫更新中", () => {
  const out = html(<WatchArea state={{ kind: "stale", previous: W }} overview={OV} requested={false} />);
  assert.ok(sectionFirst(out));
  assert.ok(out.indexOf("watch-heading") < out.indexOf(WATCH_COPY.updating));
  const empty = text(html(<WatchArea state={{ kind: "stale", previous: null }} overview={OV} requested={false} />));
  assert.match(empty, new RegExp(WATCH_COPY.updatingEmpty));
  assert.doesNotMatch(empty, /觀戰重點/);
});

test("error：有上一份時保留並提示；沒有時交給 WatchSection 錯誤態，第 1 區不受影響（不在本元件）", () => {
  const kept = html(<WatchArea state={{ kind: "error", previous: W }} overview={OV} requested={false} />);
  assert.ok(sectionFirst(kept));
  assert.match(text(kept), new RegExp(WATCH_COPY.refreshFailed));
  const none = html(<WatchArea state={{ kind: "error", previous: null }} overview={OV} requested={false} />);
  assert.ok(sectionFirst(none));
  assert.match(text(none), /第 4 區資料暫時無法讀取/);
});

test("沒有目標場（overview watch.status=no_target）：說明沒有目標場，不顯示載入中", () => {
  const o = structuredClone(OV);
  o.sections.watch = { status: "no_target", series: "C", game: null };
  const t = text(html(<WatchArea state={{ kind: "idle" }} overview={o} requested={false} />));
  assert.match(t, new RegExp(WATCH_COPY.noTarget));
});

test("watch 非 ok（例：?game 指定歷史場）：顯示 watch 自帶文字", () => {
  const hist = { ...W, status: "historical_not_published" as const, text: "歷史賽前版本尚未發布" };
  const t = text(html(<WatchArea state={{ kind: "data", data: hist }} overview={OV} requested={true} />));
  assert.match(t, /歷史賽前版本尚未發布/);
});

