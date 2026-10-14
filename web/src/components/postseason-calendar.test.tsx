import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { AnnouncedCompact, AnnouncedMobile, PostseasonCalendarLegend } from "./postseason-calendar.tsx";
import { POSTSEASON_2026 } from "@/lib/postseason-announcement.ts";
import { buildPostseasonJourney, withLiveEntries, type JourneySlot, type LiveEntryStatus } from "@/lib/postseason-journey.ts";

// #237 日曆公告格的渲染測試：可讀性修正後，格內只標例外狀態，重要限制仍在。

function text(node: ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const slots = (nowIso: string) => buildPostseasonJourney({
  announcement: POSTSEASON_2026, summary: [], rows: null, nowMs: Date.parse(nowIso), dataAsOf: "2026-10-04",
}).slots;
const byKey = (xs: JourneySlot[], k: string) => xs.find((s) => s.key === k)!;

test("手機公告格：一行主客、一行球場；不逐格掛「公告安排」；如有必要與 G3／G4 球場分支可見", () => {
  const xs = slots("2026-10-08T12:00:00+08:00");
  const e3 = text(<AnnouncedMobile s={byKey(xs, "E3")} asOf="2026-10-04" />);
  assert.match(e3, /^季後挑戰賽 G3 如有必要 17:05 開打 .*統一獅（客） 對 .*中信兄弟（主） 洲際$/);
  assert.doesNotMatch(e3, /公告安排/);
  const c3 = text(<AnnouncedMobile s={byKey(xs, "C3")} asOf="2026-10-04" />);
  assert.match(c3, /味全龍（客） 對 (待 )?挑戰賽勝隊（主） 球場依晉級隊：兄弟晉級→大巨蛋／統一晉級→亞太主/);
  assert.doesNotMatch(c3, /挑戰賽勝隊.*挑戰賽勝隊/, "未定席位只念一次");
  // G5–G7（10/08 核對官方公告）：挑戰賽勝隊為客、味全龍為主、大巨蛋、如有必要。
  const c5 = text(<AnnouncedMobile s={byKey(xs, "C5")} asOf="2026-10-04" />);
  assert.match(c5, /^台灣大賽 G5 如有必要 18:35 開打 (待 )?挑戰賽勝隊（客） 對 .*味全龍（主） 大巨蛋$/);
  assert.doesNotMatch(c5, /本站未取得/);
});

test("公告格的例外狀態仍標示：已過開賽時間 → 賽果待更新與截至；桌面格同樣只標例外", () => {
  const xs = slots("2026-10-09T21:00:00+08:00");
  const m = text(<AnnouncedMobile s={byKey(xs, "E1")} asOf="2026-10-04" />);
  assert.match(m, /季後挑戰賽 G1 賽果待更新 17:05 開打/);
  assert.match(m, /已過預定開賽時間・本站尚無賽果紀錄（本站賽果紀錄至 10\/04）/);
  assert.match(text(<AnnouncedCompact s={byKey(xs, "E1")} />), /賽果待更新/);
  const d2 = renderToStaticMarkup(<AnnouncedCompact s={byKey(xs, "E2")} />);
  assert.match(d2, /data-announced="true"/);
  assert.doesNotMatch(text(<AnnouncedCompact s={byKey(xs, "E2")} />), /公告安排/);
  assert.doesNotMatch(d2, /<a /, "公告格不給單場連結");
});

// #237 單場賽況入口：身分相符的 E1 公告格整格連到單場頁，且只有一個連結；
// 待更新說明改為「整體賽果待更新，可查看單場賽況」。快照值為 SYNTHETIC（形狀同 19:25 RECORDED）。
test("公告格有單場入口：桌面與手機整格各一個連結，待更新說明改指向單場賽況", () => {
  const base = buildPostseasonJourney({
    announcement: POSTSEASON_2026, summary: [], rows: null, nowMs: Date.parse("2026-10-09T19:25:00+08:00"), dataAsOf: "2026-10-04",
  });
  const st: LiveEntryStatus = {
    season: 2026, kind_code: "E", game_sno: 1, canonical_phase: "live",
    live_snapshot: {
      game_id: "2026-E-1", game_sno: 1, kind_code: "E", phase: "live", starts_at: "2026-10-09T17:05:00",
      away: { team: { code: "ADD011" } }, home: { team: { code: "ACN011" } },
    },
  };
  const e1 = byKey(withLiveEntries(base, { E1: st }).slots, "E1");
  for (const node of [<AnnouncedCompact s={e1} />, <AnnouncedMobile s={e1} asOf="2026-10-04" />]) {
    const html = renderToStaticMarkup(node);
    assert.equal(html.match(/<a /g)?.length, 1);
    assert.match(html, /<a [^>]*href="\/games\/1\?kind=E&amp;year=2026"/);
    assert.match(html, /data-announced="true"/);
    assert.match(text(node), /單場賽況/);
  }
  const m = text(<AnnouncedMobile s={e1} asOf="2026-10-04" />);
  assert.match(m, /整體賽果待更新，可查看單場賽況/);
  assert.doesNotMatch(m, /本站尚無賽果紀錄/);
  assert.match(m, /季後挑戰賽 G1 賽果待更新 17:05 開打/, "狀態徽章仍是資料庫判準");
  // 沒有入口的同一格：維持原樣、沒有連結。
  const plain = byKey(withLiveEntries(base, { E1: null }).slots, "E1");
  assert.doesNotMatch(renderToStaticMarkup(<AnnouncedMobile s={plain} asOf="2026-10-04" />), /<a /);
  assert.doesNotMatch(renderToStaticMarkup(<AnnouncedCompact s={plain} />), /<a /);
});

// #268 N13（#273 盤點轉入）：舊版日曆上方說明不論本月有沒有虛線公告格，一律寫「虛線框為官方公告安排
// （本站尚無正式場次，不提供單場連結）」；台灣大賽 G1–G7 入庫後是實線格、連到 /games/1..7?kind=C，
// 與說明矛盾。舊碼沒有這個元件、也沒有「本月有沒有虛線格」的分支，所以本測試在舊碼下失敗。
// 下列 E／C 列為合成（形狀同 calendar 端點），不是官方核對結果。
test("日曆季後說明：本月沒有虛線公告格時不寫「虛線框…不提供單場連結」；有時照寫", () => {
  const rows = POSTSEASON_2026.slots.map((s) => {
    const sno = s.kind === "E" ? s.officialSno! : s.seq;
    const brotherHome = s.kind === "C" && (s.seq === 3 || s.seq === 4);
    const code = (t: typeof s.away) => (t && "code" in t ? t.code : "ACN011");
    return {
      year: 2026, kind_code: s.kind, game_sno: sno, game_date: s.date, venue: "合成球場",
      away_team_code: s.kind === "C" ? (brotherHome ? "AAA011" : "ACN011") : code(s.away),
      home_team_code: s.kind === "C" ? (brotherHome ? "ACN011" : "AAA011") : code(s.home),
      away_score: 0, home_score: 0, completed: false,
    };
  });
  const j = buildPostseasonJourney({
    announcement: POSTSEASON_2026, summary: [], rows, nowMs: Date.parse("2026-10-14T12:00:00+08:00"), dataAsOf: "2026-10-12",
  });
  const announced = j.slots.filter((s) => !s.row);
  assert.equal(announced.length, 0, "合成輸入：E1–E4、C1–C7 都已對到資料庫列");
  assert.ok(j.slots.filter((s) => s.kind === "C").every((s) => s.href === `/games/${s.seq}?kind=C&year=2026`));
  const allRows = text(<PostseasonCalendarLegend journey={j} announced={announced} />);
  assert.doesNotMatch(allRows, /虛線框|不提供單場連結|尚無正式場次/);
  assert.match(allRows, /^季後賽 ： ?點線框為 ?移動補賽日/, "其餘說明照舊");
  assert.match(allRows, /系列進度與晉級條件/);

  const before = buildPostseasonJourney({
    announcement: POSTSEASON_2026, summary: [], rows: null, nowMs: Date.parse("2026-10-08T12:00:00+08:00"), dataAsOf: "2026-10-04",
  });
  const ann = before.slots.filter((s) => !s.row);
  assert.match(text(<PostseasonCalendarLegend journey={before} announced={ann} />),
    /虛線框為官方公告安排（本站尚無正式場次， ?不提供單場連結 ?）・/);
});
