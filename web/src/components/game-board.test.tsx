import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GameBoard, { type Live } from "./game-board.tsx";
import type { StatRow } from "@/lib/client.ts";
import type { LiveSnapshot } from "@/lib/live-game.ts";

// 頂部記分條的**態**渲染測試（`UX-GAME-COMPLETED-SCOREBAR1` / #160）。
//
// 守的是設計定稿 §1.1.1：完賽態總覽的中央格只寫「終場」，不畫 `▲/▼ N 局`、壘包與球數；
// 賽中態與「完賽 ＋ 逐打席」則必須照舊顯示局面。
//
// ⚠️ 為什麼四個樣本一個都不能少：
//   * 只斷言完賽側 → 一個「永遠不顯示」的實作會全綠。
//   * 只用「無 snapshot」的完賽樣本 → 寫成 `snapshot?.phase === "final"` 的實作會全綠
//     （那條路對歷史存檔場恆為 false，等於整張卡失效）。
//   * 漏掉 `view="pbp"` → 一個裸 `completed` 閘門會把逐打席頁籤的局面一起殺掉，而
//     ScoreBar 在 DOM 上位於 `{tabs}` 之前、兩個頁籤共用同一個元素。
//
// 判準一律落在**畫出來的字與 aria-label**，不落在原始碼形狀上。

// ───────── 樣本：2026-08-20 A#276（中信兄弟 4：3 味全龍）的真實 payload 逐欄照抄 ─────────
//
// ⚠️ 需要 `as unknown as StatRow`：真實 payload 的 `is_ball`／`is_strike`／`is_change_player`
// 等欄位是 **boolean**，而 `lib/client.ts` 的 `StatRow` 只宣告 `number | string | null`。
// 這裡刻意保留 boolean 原值而不改成 0/1——`GameBoard` 的逐打席彙總會讀 `is_change_player`，
// 型別遷就會讓樣本走到與生產不同的分支。

/** 6 局上、1 出局、B2 S2、一壘有人、3：0（賽中樣本）。 */
const LIVE_EVENT = {
  action_name: "一壘安打 ", ball_cnt: 2, batting_action_name: "一安", batting_order: 3,
  catcher_acnt: "0000006217", catcher_name: "林辰勳",
  content: "壞球。 一壘跑者高宇杰 盜壘上二壘。", defend_station_code: "2B",
  first_base: "8", second_base: null, third_base: null,
  game_sno: 276, hitter_acnt: "0000002291", hitter_name: "岳東華", home_score: 0,
  inning_seq: 6, is_ball: true, is_change_player: false, is_score: false,
  is_special_event: false, is_strike: false, kind_code: "A", main_event_no: "0610014000",
  out_cnt: 1, pitch_cnt: 109, pitcher_acnt: "0000007264", pitcher_name: "魔神龍",
  strike_cnt: 2, visiting_home_type: "1", visiting_score: 3, year: 2026,
} as unknown as StatRow;

/** 末筆事件：9 局下、2 出局、B2 S2、二壘有人、4：3、`content="比賽結束"`。
 *  ⚠️ `out_cnt` 是**打席前**計數，所以這筆描述的是「最後一個出局發生之前」的局面
 *  ——正是 #160 的痛點：完賽後把它畫出來等於陳述一件假的事。 */
const FINAL_EVENT = {
  action_name: "野手接球自踩壘包 一壘", ball_cnt: 2, batting_action_name: "一滾", batting_order: 5,
  catcher_acnt: "0000002285", catcher_name: "高宇杰",
  content: "比賽結束", defend_station_code: "CF",
  first_base: null, second_base: "9", third_base: null,
  game_sno: 276, hitter_acnt: "0000005549", hitter_name: "郭天信", home_score: 3,
  inning_seq: 9, is_ball: false, is_change_player: false, is_score: false,
  is_special_event: true, is_strike: true, kind_code: "A", main_event_no: "0920023000",
  out_cnt: 2, pitch_cnt: 21, pitcher_acnt: "0000003331", pitcher_name: "李振昌",
  strike_cnt: 2, visiting_home_type: "2", visiting_score: 4, year: 2026,
} as unknown as StatRow;

const GAME = {
  year: 2026, kind_code: "A", game_sno: 276, game_date: "2026-08-20", venue: "大巨蛋",
  away_team_code: "ACN011", away_team_name: "中信兄弟",
  home_team_code: "AAA011", home_team_name: "味全龍",
  delay_kind: null, orig_date: null, present_status: 1,
};

/** ScoreBar 只讀 `phase`／`inning`／`half`／`event_count`／`source.fetched_at`；
 *  其餘欄位（away／home box 等）由頁面層的 `applyLiveSnapshot` 消費，不進本元件，
 *  故此處只給前述欄位並轉型。**賽中樣本本身就是這個轉型的正向對照**——若欄位不足
 *  以走到賽中分支，賽中側的三項斷言會先失敗。 */
const snapshot = (phase: "live" | "final", inning: number, half: string): LiveSnapshot =>
  ({
    game_id: "20260820276", game_sno: 276, kind_code: "A", phase,
    raw_status: null, inning, half, event_count: 300,
    freshness: phase === "final" ? "final" : "fresh", source_status: "ok",
    source: { fetched_at: "2026-08-20T21:30:00+08:00" },
  }) as unknown as LiveSnapshot;

function data(over: Partial<Live> = {}): Live {
  return {
    game: GAME as unknown as StatRow,
    scoreboard: [], livelog: [LIVE_EVENT, FINAL_EVENT],
    batting: [], pitching: [], people: {},
    records: { ACN011: { w: 35, l: 51, form: "7-3" }, AAA011: { w: 55, l: 34, form: "5-5" } },
    batter_avg: {}, detail: null, has_tracking: false, tracking: [],
    live_snapshot: null,
    ...over,
  } as Live;
}

// ───────── 取「記分條」那一段 markup ─────────

/** ScoreBar 渲染於 `{tabs}` **之前**（兩個頁籤共用同一個元素）。用一個 sentinel 當作
 *  切點，讓每一條斷言都只看記分條，不會被逐打席區塊裡的壘包圖／局數文字誤判成通過。 */
function scorebar(node: ReactElement): string {
  const html = renderToStaticMarkup(node);
  const cut = html.indexOf('id="tabs-sentinel"');
  assert.ok(cut > 0, "tabs sentinel 必須出現在輸出中（ScoreBar 應渲染於 tabs 之前）");
  return html.slice(0, cut);
}

function board(over: {
  view: "overview" | "pbp"; idx: number;
  snapshot?: LiveSnapshot | null; awayScore: number; homeScore: number;
}): string {
  return scorebar(
    <GameBoard
      data={data({
        live_snapshot: over.snapshot ?? null,
        game: { ...GAME, away_score: over.awayScore, home_score: over.homeScore } as unknown as StatRow,
      })}
      idx={over.idx} setIdx={() => {}} view={over.view} gameSno="276"
      tabs={<hr id="tabs-sentinel" />} />,
  );
}

/** 球數燈：`Dots` 是記分條裡唯一產生這個 class 的地方（賽中 B 三顆 + S 兩顆 = 5）。 */
const countDots = (html: string) =>
  html.split('class="h-2.5 w-2.5 rounded-full border"').length - 1;

/** 取記分條**中央格**（grid 的第三欄）的 markup，用標籤配對切出整格。
 *
 *  ⚠️ 為什麼一定要切到這一格才斷言 `▲`／`▼`：記分條第一列（狀態列）在**有 snapshot**
 *  的完賽場會顯示「比賽結束　▼ 9 局」，而需求方 2026-08-21 裁定該列**保留不動**——那裡
 *  的半局符號緊鄰 phase 標籤，讀作「在第 9 局下結束」（F/9 慣例），與中央格「正在進行中
 *  的 BOT 9」語意不同。在整條記分條上斷言 `▲`／`▼` 不存在會誤殺那一列。 */
function centerCell(html: string): string {
  // 前綴比對：完賽態的中央格不掛 px-2（見 game-board.tsx 該處註解），故不能比對整串 class。
  const at = html.indexOf('class="flex flex-col items-center gap-0.5');
  assert.ok(at > 0, "記分條中央格必須存在");
  let i = html.indexOf(">", at) + 1;
  const start = i;
  for (let depth = 1; depth > 0; ) {
    const open = html.indexOf("<div", i);
    const close = html.indexOf("</div>", i);
    assert.ok(close > 0, "中央格必須閉合");
    if (open >= 0 && open < close) { depth++; i = open + 4; } else { depth--; i = close + 6; }
  }
  return html.slice(start, i - 6);
}

/** 取畫面上的可讀文字（沿用 today-slate.test.tsx 的判準：只看讀者看得到的字）。 */
const text = (html: string) =>
  html.replace(/<[^>]*>/g, " ").replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();

/** 完賽 ＋ 總覽：中央格只剩「終場」。 */
const FINAL_OVERVIEW = { view: "overview", idx: 1, awayScore: 4, homeScore: 3 } as const;
/** 完賽 ＋ 逐打席：局面必須留著（該頁籤的核心資訊）。 */
const FINAL_PBP = { view: "pbp", idx: 1, awayScore: 4, homeScore: 3 } as const;
/** 賽中 ＋ 總覽。 */
const LIVE_OVERVIEW = { view: "overview", idx: 0, awayScore: 3, homeScore: 0 } as const;

function assertSituationHidden(html: string, label: string) {
  const cell = centerCell(html);
  // 中央格的可讀文字必須**恰好**是「終場」——不是「含有」，避免局面殘留還讓斷言通過。
  assert.equal(text(cell), "終場", `${label}：中央格必須只剩「終場」`);
  assert.ok(!cell.includes("▲") && !cell.includes("▼"), `${label}：中央格不得出現半局符號`);
  assert.equal(countDots(cell), 0, `${label}：中央格不得出現球數燈`);
  // 以下三項在整條記分條上斷言：TOP／BOT 與壘包圖只由中央格產生，
  // 任何一處殘留都代表態閘門沒接上。
  assert.ok(!html.includes("TOP"), `${label}：記分條不得出現 TOP`);
  assert.ok(!html.includes("BOT"), `${label}：記分條不得出現 BOT`);
  assert.ok(!html.includes('aria-label="壘上'),
    `${label}：記分條不得留下壘包／出局的 aria-label（螢幕閱讀器受害面）`);
  assert.ok(!html.includes("出局"), `${label}：記分條不得出現出局數`);
}

function assertSituationShown(html: string, label: string, half: "▲ TOP" | "▼ BOT", inning: string) {
  const cell = centerCell(html);
  assert.equal(text(cell), `${half} ${inning} B S`, `${label}：中央格必須是完整的賽中局面`);
  assert.ok(cell.includes('aria-label="壘上'), `${label}：中央格必須顯示壘包／出局`);
  assert.equal(countDots(cell), 5, `${label}：中央格必須顯示 B 三顆 + S 兩顆球數燈`);
  assert.ok(!cell.includes("終場"), `${label}：中央格不得顯示「終場」`);
}

// ───────── (a) 完賽側：三樣都不得出現 ─────────

test("完賽（歷史存檔場，無 snapshot）＋總覽：記分條只呈現終場比分", () => {
  const html = board({ ...FINAL_OVERVIEW, snapshot: null });
  assertSituationHidden(html, "完賽・無 snapshot");
  // 比分本身必須還在——移除的是局面，不是比分。
  assert.ok(html.includes(">4<") && html.includes(">3<"), "終場比分 4：3 必須仍然顯示");
  assert.ok(html.includes("中信兄弟") && html.includes("味全龍"), "兩隊識別必須仍然顯示");
});

test("完賽（當日場，snapshot.phase=final）＋總覽：記分條只呈現終場比分", () => {
  // ⚠️ 這一條與上一條**走不同的 completed 路徑**：
  //    canShowPostgameConclusions = scoreTotal > 0 && (snapshot === null || phase === "final")
  //    兩條都必須成立，實作才不能靠單一路徑蒙混。
  const html = board({ ...FINAL_OVERVIEW, snapshot: snapshot("final", 9, "2") });
  assertSituationHidden(html, "完賽・snapshot=final");
  assert.ok(html.includes("比賽結束"), "狀態列的 phase 標籤不在本卡射程內，必須保持顯示");
});

// ───────── (b) 賽中側：三樣都必須出現 ─────────

test("賽中（snapshot.phase=live）＋總覽：局面照舊顯示", () => {
  const html = board({ ...LIVE_OVERVIEW, snapshot: snapshot("live", 6, "1") });
  assertSituationShown(html, "賽中", "▲ TOP", "6");
  assert.ok(html.includes("比賽進行中"), "狀態列必須顯示比賽進行中");
});

// ───────── (c) 誤傷防線：逐打席頁籤不受影響 ─────────

test("完賽＋逐打席：選中打席的局面仍然顯示（ScoreBar 與賽後戰報共用同一元素）", () => {
  const html = board({ ...FINAL_PBP, snapshot: null });
  assertSituationShown(html, "完賽・逐打席", "▼ BOT", "9");
});

test("完賽＋逐打席（當日場 snapshot=final）：局面同樣不得被關掉", () => {
  const html = board({ ...FINAL_PBP, snapshot: snapshot("final", 9, "2") });
  assertSituationShown(html, "完賽・逐打席・snapshot=final", "▼ BOT", "9");
});
