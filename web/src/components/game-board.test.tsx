import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GameBoard, { type Live } from "./game-board.tsx";
import type { StatRow } from "@/lib/client.ts";
import { applyLiveSnapshot, type LiveApiResponse, type LiveSnapshot } from "@/lib/live-game.ts";
import type { PaFact } from "@/lib/game-facts.ts";

// ───── #237 投手卡累計球數（純合成：年份 2031、場號 901、選手與事件皆虛構，非實際來源觀測）─────
type PcPitch = {
  evt?: string | undefined; pitcher: string; pitchCnt?: unknown; content: string;
  inning?: number; change?: boolean; strike?: boolean; hitter?: string;
};
const pcRow = ({ evt, pitcher, pitchCnt, content, inning = 1, change = false, strike = !change, hitter }: PcPitch) => ({
  ...(evt === undefined ? {} : { MainEventNo: evt }), VisitingHomeType: "1", InningSeq: inning, VisitingScore: 0, HomeScore: 0,
  IsChangePlayer: change ? "1" : "0", IsStrike: strike ? "1" : "0", Content: content,
  HitterAcnt: change ? "" : hitter ?? "H01", HitterName: change ? "" : "虛構打者",
  PitcherAcnt: pitcher, PitcherName: pitcher === "PA01" ? "虛構投手甲" : "虛構投手乙",
  ...(pitchCnt === undefined ? {} : { PitchCnt: pitchCnt }),
});
const pcSide = (code: string, name: string): LiveSnapshot["home"] => ({
  team: { code, name }, score: 0, inning_score: [{ Seq: 1, Score: "0" }],
  lineup: { availability: "announced", items: [], first_observed_at: null },
  hitters: [], pitchers: [], probable_pitcher: { availability: "not_announced" },
});
const pcSnapshot = (rows: PcPitch[]): LiveSnapshot => ({
  game_id: "2031-A-901", game_sno: 901, kind_code: "A", phase: "live", raw_status: "START",
  inning: 1, half: "top", event_count: rows.length, tracking_count: 0,
  tracking_availability: "pending", poll_after_seconds: 12, freshness: "fresh", source_status: "ok",
  stale_after_seconds: 45, source: { fetched_at: "2031-07-01T11:00:00+00:00", version: "pc-v1" },
  away: pcSide("AAA", "虛構客隊"), home: pcSide("BBB", "虛構主隊"),
  livelog: rows.map(pcRow),
});
/** 實際 SSR 渲染 GameBoard（逐打席視圖），回傳投手橫幅「…K・被安N・X球」的 X。 */
const pcCard = (rows: PcPitch[], idx: number): string | undefined => {
  const raw: LiveApiResponse = {
    game: { year: 2031, kind_code: "A", game_sno: 901 },
    scoreboard: [], livelog: [], batting: [], pitching: [], people: {}, records: {}, batter_avg: {},
    detail: null, decisions: {}, decision_counts: null, has_tracking: false, tracking: [], spray: [],
    live_snapshot: pcSnapshot(rows),
  };
  const data = applyLiveSnapshot(raw) as unknown as Live;
  const html = renderToStaticMarkup(
    <GameBoard data={data} idx={idx} setIdx={() => {}} view="pbp" gameSno="901" />,
  ).replace(/<!-- -->/g, "");
  return /K・被安\d+・([^<]*?)球/.exec(html)?.[1];
};
const pcPitcherA = (): PcPitch[] => [
  ...Array.from({ length: 18 }, (_, i): PcPitch => {
    const n = i + 1;
    const inInning = (n - 1) % 9 + 1;
    const outs = inInning % 3 === 0 ? inInning / 3 : 0;
    return { evt: String(n), pitcher: "PA01", pitchCnt: n, inning: n <= 9 ? 1 : 2,
             content: outs ? `三振，${outs}人出局。` : "好球。" };
  }),
  // 同一第 18 球的第二列：結束公告（同事件鍵、同 pitch_cnt，官方判決旗標同樣為好球）
  { evt: "18", pitcher: "PA01", pitchCnt: 18, inning: 2, content: "比賽結束。" },
];

test("#237 投手卡累計球數取 pitch_cnt：同一球兩列（三人出局＋結束公告）顯示 18 而非 19", () => {
  const rows = pcPitcherA();
  assert.equal(pcCard(rows, rows.length - 1), "18", "結束公告列不得再算一球");
  assert.equal(pcCard(rows, rows.length - 2), "18");
  assert.equal(pcCard(rows, 15), "16", "選中第 16 球只算到當時，不把整場總數填入早期事件");
  assert.equal(pcCard(rows, 0), "1");
});

test("#237 投手卡球數：換投隔離、無球未知、0 為已知值", () => {
  const rows: PcPitch[] = [
    { evt: "1", pitcher: "PA01", pitchCnt: 1, content: "好球。" },
    { evt: "2", pitcher: "PA01", pitchCnt: 2, content: "好球。" },
    { evt: "3", pitcher: "PA01", pitchCnt: 3, content: "三振，1人出局。" },
    { evt: "4", pitcher: "PB02", content: "投手異動：虛構投手乙接替。", change: true },
    { evt: "5", pitcher: "PB02", pitchCnt: 0, content: "牽制。", strike: false },
    { evt: "6", pitcher: "PB02", pitchCnt: 1, content: "好球。" },
    { evt: "7", pitcher: "PB02", pitchCnt: 2, content: "好球。" },
  ];
  assert.equal(pcCard(rows, 2), "3");
  assert.equal(pcCard(rows, 3), "—", "換投當下新投手尚無任何 pitch_cnt：未知，不寫 0");
  assert.equal(pcCard(rows, 4), "0", "官方 pitch_cnt=0 是已知值");
  assert.equal(pcCard(rows, 6), "2", "換投後只算新投手，不混入前任");
});

test("#237 投手卡球數：pitch_cnt 缺值／無效／倒退不造數，不以判決旗標逐列補算", () => {
  const invalid: PcPitch[] = [null, "", "2.5", 2.5, -1].map((pitchCnt, i) => ({
    evt: String(i + 1), pitcher: "PA01", pitchCnt, content: "好球。",
  }));
  assert.equal(pcCard(invalid, invalid.length - 1), "—");
  const absent: PcPitch[] = ["1", "2", "3"].map((evt) => ({ evt, pitcher: "PA01", content: "好球。" }));
  assert.equal(pcCard(absent, 2), "—", "缺 pitch_cnt 不得以 is_strike 逐列計數");
  const trailing: PcPitch[] = [
    { evt: "1", pitcher: "PA01", pitchCnt: 1, content: "好球。" },
    { evt: "2", pitcher: "PA01", pitchCnt: 2, content: "三振，1人出局。" },
    { evt: "2", pitcher: "PA01", content: "比賽結束。" },
  ];
  assert.equal(pcCard(trailing, 2), "2", "同球後續列缺 pitch_cnt：沿用當時最近已知值");
  const laterInvalid: PcPitch[] = [
    { evt: "1", pitcher: "PA01", pitchCnt: 1, content: "好球。" },
    { evt: "2", pitcher: "PA01", pitchCnt: null, content: "好球。" },
  ];
  assert.equal(pcCard(laterInvalid, 1), "—", "已知值之後的明示無效值：未知，不吞成最近已知值");
  const regressed: PcPitch[] = [1, 2, 3, 4, 5, 3].map((pitchCnt, i) => ({
    evt: String(i + 1), pitcher: "PA01", pitchCnt, content: "好球。",
  }));
  assert.equal(pcCard(regressed, 4), "5");
  assert.equal(pcCard(regressed, 5), "—", "累計倒退屬不正常資料：未知，不顯示倒退值");
});

test("#237 投手卡球數：事件鍵缺／空字串／純空白不能證明同一球，後續缺 pitch_cnt 列不得沿用前值", () => {
  const omitted: PcPitch[] = [
    { pitcher: "PA01", pitchCnt: 7, content: "三振，3人出局。" },
    { pitcher: "PA01", content: "比賽結束。" },
  ];
  assert.equal(pcCard(omitted, 0), "7", "本列明示有效 pitch_cnt：事件鍵缺也照常顯示");
  assert.equal(pcCard(omitted, 1), "—", "兩列都缺 MainEventNo：無法證明同一球，未知");
  for (const evt of ["", " ", "  \t "]) {
    const rows: PcPitch[] = [
      { evt, pitcher: "PA01", pitchCnt: 7, content: "三振，3人出局。" },
      { evt, pitcher: "PA01", content: "比賽結束。" },
    ];
    const label = `MainEventNo=${JSON.stringify(evt)}`;
    assert.equal(pcCard(rows, 0), "7", `${label}：本列明示有效值照常顯示`);
    assert.equal(pcCard(rows, 1), "—", `${label}：空或純空白事件鍵不能證明同一球`);
  }
  // 對照：有效且相同事件鍵可沿用；有效但不同事件鍵不沿用
  const sameEvent: PcPitch[] = [
    { evt: "E1", pitcher: "PA01", pitchCnt: 7, content: "三振，3人出局。" },
    { evt: "E1", pitcher: "PA01", content: "比賽結束。" },
  ];
  assert.equal(pcCard(sameEvent, 1), "7", "有效且相同事件鍵：同一球後續列沿用");
  const otherEvent: PcPitch[] = [
    { evt: "E1", pitcher: "PA01", pitchCnt: 7, content: "好球。" },
    { evt: "E2", pitcher: "PA01", content: "好球。" },
  ];
  assert.equal(pcCard(otherEvent, 1), "—", "不同事件鍵：未知，不沿用");
  // 明示有效值（含 0）不受事件鍵缺／空／純空白影響
  for (const evt of [undefined, "", "  "]) {
    const zero: PcPitch[] = [{ evt, pitcher: "PA01", pitchCnt: 0, content: "牽制。", strike: false }];
    assert.equal(pcCard(zero, 0), "0", `MainEventNo=${JSON.stringify(evt)}：0 是已知值`);
    const twoKnown: PcPitch[] = [
      { evt, pitcher: "PA01", pitchCnt: 6, content: "好球。" },
      { evt, pitcher: "PA01", pitchCnt: 7, content: "好球。" },
    ];
    assert.equal(pcCard(twoKnown, 1), "7", `MainEventNo=${JSON.stringify(evt)}：本列明示值優先`);
  }
});

// ───── #237 逐打席卡打席用球數（同一組純合成工廠；E30／E31 等事件鍵與選手皆虛構）─────
/** 實際 SSR 渲染逐打席視圖的 HTML（與 pcCard 同一條渲染路徑）。 */
const pcPaHtml = (rows: PcPitch[], idx: number, facts?: PaFact[] | null): string => {
  const raw: LiveApiResponse = {
    game: { year: 2031, kind_code: "A", game_sno: 901 },
    scoreboard: [], livelog: [], batting: [], pitching: [], people: {}, records: {}, batter_avg: {},
    detail: null, decisions: {}, decision_counts: null, has_tracking: false, tracking: [], spray: [],
    live_snapshot: pcSnapshot(rows),
  };
  const data = applyLiveSnapshot(raw) as unknown as Live;
  return renderToStaticMarkup(
    <GameBoard data={data} idx={idx} setIdx={() => {}} view="pbp" gameSno="901" facts={facts} />,
  ).replace(/<!-- -->/g, "");
};
/** 依畫面順序回傳各打席卡「（N 球）」的 N；未標示球數的打席不出現在陣列中。 */
const pcPaLabels = (rows: PcPitch[], idx: number, facts?: PaFact[] | null): string[] =>
  [...pcPaHtml(rows, idx, facts).matchAll(/（(\d+) 球）/g)].map((m) => m[1] ?? "");
/** 同一打席（同打者、同一有效事件鍵 E30）四球，累計 21–24；第 24 球後另有重複 24 的結束公告列。 */
const pcPaRows = (): PcPitch[] => [
  { evt: "E30", pitcher: "PA01", pitchCnt: 21, content: "好球。" },
  { evt: "E30", pitcher: "PA01", pitchCnt: 22, content: "壞球。", strike: false },
  { evt: "E30", pitcher: "PA01", pitchCnt: 23, content: "界外。" },
  { evt: "E30", pitcher: "PA01", pitchCnt: 24, content: "三振，3人出局。" },
  { evt: "E30", pitcher: "PA01", pitchCnt: 24, content: "比賽結束。" },
];

test("#237 逐打席卡球數依投手累計 pitch_cnt：四球＋重複 24 的結束公告顯示 4 球，而非來源列數 5", () => {
  const rows = pcPaRows();
  const last = rows.length - 1;
  assert.deepEqual(pcPaLabels(rows, last), ["4"], "結束公告重複同一累計值，不得多算一球");
  assert.equal(pcCard(rows, last), "24", "投手卡累計維持 24，與打席 4 球（21–24）一致");
  const html = pcPaHtml(rows, last);
  assert.ok(html.includes("三振，3人出局。"), "第三出局列保留");
  assert.ok(html.includes("比賽結束。"), "結束公告列保留，不因去重而消失");
});

test("#237 逐打席卡球數：逐打席各自計算，早段選中也是整個打席用球，不是全場累計", () => {
  const rows: PcPitch[] = [
    ...pcPaRows().slice(0, 3),
    { evt: "E30", pitcher: "PA01", pitchCnt: 24, content: "三振，1人出局。" },
    { evt: "E31", hitter: "H02", pitcher: "PA01", pitchCnt: 25, content: "壞球。", strike: false },
    { evt: "E31", hitter: "H02", pitcher: "PA01", pitchCnt: 26, content: "飛球接殺，2人出局。" },
    { evt: "E31", hitter: "H02", pitcher: "PA01", pitchCnt: 26, content: "比賽結束。" },
  ];
  assert.deepEqual(pcPaLabels(rows, rows.length - 1), ["4", "2"]);
  assert.deepEqual(pcPaLabels(rows, 0), ["4", "2"], "選中第一打席首球：仍是各打席總球數，不截斷、不填 24／26");
});

test("#237 逐打席卡球數：打席中換投以（投手, pitch_cnt）區分，相同累計值不互相吞掉", () => {
  const rows: PcPitch[] = [
    { evt: "E40", pitcher: "PA01", pitchCnt: 1, content: "好球。" },
    { evt: "E40", pitcher: "PA01", pitchCnt: 2, content: "壞球。", strike: false },
    { evt: "E40", pitcher: "PB02", pitchCnt: 1, content: "好球。" },
    { evt: "E40", pitcher: "PB02", pitchCnt: 2, content: "三振，3人出局。" },
    { evt: "E40", pitcher: "PB02", pitchCnt: 2, content: "比賽結束。" },
  ];
  assert.deepEqual(pcPaLabels(rows, rows.length - 1), ["4"], "前後任各 2 球；只按累計值去重會誤成 2，按列數會誤成 5");
});

test("#237 逐打席卡球數：缺值／null／無效／倒退時不標示球數，不以列數補算、不寫 0", () => {
  const base = pcPaRows();
  const withCnt = (i: number, pitchCnt: unknown): PcPitch[] =>
    base.map((row, k) => (k === i ? { ...row, pitchCnt } : row));
  const cases: [string, PcPitch[]][] = [
    ["中段明示 null", withCnt(1, null)],
    ["中段空字串", withCnt(1, "")],
    ["中段非整數", withCnt(1, "22.5")],
    ["中段負數", withCnt(1, -1)],
    ["中段缺 PitchCnt", withCnt(1, undefined)],
    ["打席內倒退", withCnt(2, 21)],
    ["整打席皆缺", base.map((row) => ({ ...row, pitchCnt: undefined }))],
  ];
  for (const [label, rows] of cases) {
    assert.deepEqual(pcPaLabels(rows, rows.length - 1), [], label);
  }
});

/** 合成 canonical 打席（公開 PaFact 契約欄位全數給定；契約無球數欄，此處也不另加）。 */
const pcFact = (memberEventNos: string[], paIndex: number): PaFact => ({
  pa_id: `2031-A-901-PA${paIndex}`, pa_index: paIndex, state: "ready", inning: 1, half: "1",
  outs_before: 2, bases_before: [], away_score_before: 0, home_score_before: 0,
  away_score_after: 0, home_score_after: 0, hitter: null, end_hitter: null, pitcher: null,
  result_action: null, outcome_family: null,
  start_event_no: memberEventNos[0] ?? null, end_event_no: memberEventNos[memberEventNos.length - 1] ?? null,
  member_event_nos: memberEventNos, runs_on_play: 0, delta_re24: null, unavailable_reason: null,
  garbage_time: false,
});

test("#237 逐打席卡球數：canonical 與近似切法共用同一計算；分組邊界各依原契約", () => {
  // 打席中途代打（H01→H09）：canonical 成員同屬 E50 一個打席；近似切法依打者切成兩段
  const rows: PcPitch[] = [
    { evt: "E50", pitcher: "PA01", pitchCnt: 21, content: "好球。" },
    { evt: "E50", pitcher: "PA01", pitchCnt: 22, content: "壞球。", strike: false },
    { evt: "E50", hitter: "H09", pitcher: "PA01", pitchCnt: 23, content: "界外。" },
    { evt: "E50", hitter: "H09", pitcher: "PA01", pitchCnt: 24, content: "三振，3人出局。" },
    { evt: "E50", hitter: "H09", pitcher: "PA01", pitchCnt: 24, content: "比賽結束。" },
  ];
  const last = rows.length - 1;
  const facts = [pcFact(["E50"], 0)];
  assert.deepEqual(pcPaLabels(rows, last, facts), ["4"], "canonical 單一打席：4 球，結束公告不多算");
  const html = pcPaHtml(rows, last, facts);
  assert.ok(html.includes("三振，3人出局。") && html.includes("比賽結束。"), "canonical 下來源列全數保留");
  assert.deepEqual(pcPaLabels(rows, last), ["2", "2"], "無 facts：兩段各依累計值計（後段以前段 22 為起點）");
  const missing = rows.map((row, k) => (k === 1 ? { ...row, pitchCnt: null } : row));
  assert.deepEqual(pcPaLabels(missing, last, facts), [], "canonical 下缺值同樣不標示");
});

test("#237 逐打席卡球數：投手無前值、打席首列是帶前一累計 20 的牽制，不得算成一球", () => {
  const pickoff: PcPitch = { evt: "E60", pitcher: "PA01", pitchCnt: 20, content: "牽制。", strike: false };
  const rows: PcPitch[] = [pickoff, ...pcPaRows().map((row) => ({ ...row, evt: "E60" }))];
  const last = rows.length - 1;
  const labels = pcPaLabels(rows, last);
  assert.notDeepEqual(labels, ["5"], "首列牽制不是投球，不得把 20 算進本打席");
  assert.deepEqual(labels, [], "投手無前值時無法證明 20 是否本打席所投：誠實不標示");
  const html = pcPaHtml(rows, last);
  assert.ok(html.includes("牽制。") && html.includes("比賽結束。"), "牽制與結束公告來源列都保留");
  // 對照：同一投手已有前值 20（前一打席）→ 20 只是起點，本打席 4 球
  const withPrior: PcPitch[] = [
    { evt: "E59", hitter: "H02", pitcher: "PA01", pitchCnt: 20, content: "飛球接殺，1人出局。" },
    ...rows,
  ];
  assert.deepEqual(pcPaLabels(withPrior, withPrior.length - 1), ["4"]);
  // 對照：首列有明示投球旗標（好球）→ 20 是本打席第一球，共 5 球
  const ledByPitch: PcPitch[] = [{ ...pickoff, content: "好球。", strike: true }, ...rows.slice(1)];
  assert.deepEqual(pcPaLabels(ledByPitch, ledByPitch.length - 1), ["5"]);
});


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

/** 球數燈：`GameSituation` 的 B／S 兩列燈號（`data-l="b"`／`"s"`；賽中 B 三顆 + S 兩顆 = 5）。
 *  #220 起出局改為同一組燈號的 O 列（`data-l="o"`），不計入本函式。 */
const countDots = (html: string) =>
  (html.match(/data-l="[bs]"/g) ?? []).length;

/** 取記分條**中央格**（grid 的第三欄）的 markup，用標籤配對切出整格。
 *
 *  ⚠️ 為什麼一定要切到這一格才斷言 `▲`／`▼`：記分條第一列（狀態列）在**有 snapshot**
 *  的完賽場會顯示「比賽結束　▼ 9 局」，而需求方 2026-08-21 裁定該列**保留不動**——那裡
 *  的半局符號緊鄰 phase 標籤，讀作「在第 9 局下結束」（F/9 慣例），與中央格「正在進行中
 *  的 BOT 9」語意不同。在整條記分條上斷言 `▲`／`▼` 不存在會誤殺那一列。 */
function centerCell(html: string): string {
  // 以 data-testid 定位（#220 起中央格 class 依態不同，不比對 class 字串）。
  const at = html.indexOf('data-testid="scorebar-center"');
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
  assert.ok(!/aria-label="[^"]*(壘上|有人|滿壘)/.test(html),
    `${label}：記分條不得留下壘包的 aria-label（螢幕閱讀器受害面）`);
  assert.ok(!html.includes("出局"), `${label}：記分條不得出現出局數`);
}

function assertSituationShown(html: string, label: string, half: "上" | "下", inning: string) {
  const cell = centerCell(html);
  assert.equal(text(cell), `${inning} 局${half} B S O`, `${label}：中央格必須是完整的賽中局面`);
  assert.ok(/aria-label="[^"]*(壘上無人|有人|滿壘)/.test(cell), `${label}：中央格必須顯示壘包`);
  assert.ok(/aria-label="[^"]*出局"/.test(cell), `${label}：中央格必須顯示出局數`);
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
  assertSituationShown(html, "賽中", "上", "6");
  assert.ok(html.includes("比賽進行中"), "狀態列必須顯示比賽進行中");
});

// ───────── (c) 誤傷防線：逐打席頁籤不受影響 ─────────

test("完賽＋逐打席：選中打席的局面仍然顯示（ScoreBar 與賽後戰報共用同一元素）", () => {
  const html = board({ ...FINAL_PBP, snapshot: null });
  assertSituationShown(html, "完賽・逐打席", "下", "9");
});

test("完賽＋逐打席（當日場 snapshot=final）：局面同樣不得被關掉", () => {
  const html = board({ ...FINAL_PBP, snapshot: snapshot("final", 9, "2") });
  assertSituationShown(html, "完賽・逐打席・snapshot=final", "下", "9");
});

// ───────── #210：完賽後賽中擷取逐球的揭露（真實 A-227 worker 產出） ─────────

function carriedBoard(over: { dbTracking?: boolean; estimate?: "all" | "none"; eventNo: string }): string {
  const snap = JSON.parse(readFileSync(
    new URL("../lib/__fixtures__/live_snapshot_2026-A-227_final_carryover.json", import.meta.url), "utf8",
  )) as LiveSnapshot & { livelog: { trackman?: Record<string, unknown> | null }[] };
  if (over.estimate === "all") for (const row of snap.livelog) if (row.trackman) row.trackman.pitch_type_est = "四縫";
  const applied = applyLiveSnapshot({
    ...data(), game: null, livelog: [], live_snapshot: { ...snap, freshness: "final", source_status: "ok" },
    has_tracking: Boolean(over.dbTracking),
    tracking: over.dbTracking ? [{ main_event_no: over.eventNo, pitch_cnt: 1, pitch_call: "BallCalled" }] : [],
  } as unknown as LiveApiResponse) as unknown as Live;
  const idx = applied.livelog.findIndex((row) => row.main_event_no === over.eventNo);
  assert.ok(idx >= 0, `fixture 必須含事件 ${over.eventNo}`);
  return text(renderToStaticMarkup(
    <GameBoard data={applied} idx={idx} setIdx={() => {}} view="pbp" gameSno="227" tabs={null} />,
  ));
}

test("完賽＋DB 無逐球：逐球面板揭露賽中擷取、N／M 球、缺球打席 x／y 與本打席缺球", () => {
  const html = carriedBoard({ eventNo: "0310012000" });
  assert.match(html, /賽中擷取 ・已取得 273／274 球・缺球打席 1／\d+/);
  assert.match(html, /本打席缺 1 球/);
  assert.match(html, /本場正式逐球尚未入庫，此為比賽中擷取/);
  assert.match(html, /正式逐球入庫後改用正式資料/);
  // 不得斷言官方目前的發布狀態（顯示期間官方可能已重新發布、只是尚未入庫）。
  assert.doesNotMatch(html, /尚未重新發布/);
  // 沿用快照沒有推算時整打席退回官網分類（既有 PA 來源鎖定）。
  assert.match(html, /球種：官網分類/);
});

test("完賽＋DB 無逐球：整打席都有推算才標「球種：推算」；完整打席不標缺球", () => {
  const html = carriedBoard({ eventNo: "0110001000", estimate: "all" });
  assert.match(html, /球種：推算/);
  assert.match(html, /賽中擷取/);
  assert.doesNotMatch(html, /本打席缺/);
});

test("完賽＋DB 有逐球：不出現賽中擷取揭露", () => {
  const html = carriedBoard({ eventNo: "0110001000", dbTracking: true });
  assert.doesNotMatch(html, /賽中擷取/);
});

// ───────── #237：2026 季後 E／C，snapshot=null 不得只憑比分進入完賽態 ─────────
// E1 比分抄自官方 2026-10-09 17:52 擷取（PresentStatus=1、GameResult=''、HomeScore=3、VisitingScore=0）；
// 逐打席事件沿用上方 A#276 的真實樣本（僅作版面驅動，**不代表 E1 的實際局面**）。
function postseasonBoard(game: Record<string, unknown>, idx: number): string {
  return scorebar(
    <GameBoard
      data={data({ live_snapshot: null, game: { ...GAME, ...game } as unknown as StatRow })}
      idx={idx} setIdx={() => {}} view="overview" gameSno="1"
      tabs={<hr id="tabs-sentinel" />} />,
  );
}

test("#237 E 2026＋snapshot=null＋3:0＋官方未定案：記分條不得收成「終場」", () => {
  const html = postseasonBoard({ kind_code: "E", year: 2026, game_sno: 1, away_score: 0, home_score: 3, completed: false }, 0);
  assertSituationShown(html, "E 官方未定案", "上", "6");
});

test("#237 E 2026＋舊 API（無 completed 欄）：同樣不得收成「終場」", () => {
  const html = postseasonBoard({ kind_code: "E", year: 2026, game_sno: 1, away_score: 0, home_score: 3 }, 0);
  assertSituationShown(html, "E 無 completed", "上", "6");
});

test("#237 E 2026＋官方 completed：才收成「終場」", () => {
  const html = postseasonBoard({ kind_code: "E", year: 2026, game_sno: 1, away_score: 4, home_score: 3, completed: true }, 1);
  assertSituationHidden(html, "E 官方完賽");
});

test("#237 A 基準不變：同樣 snapshot=null＋3:0（completed 欄即使為 false）仍走比分判斷", () => {
  const html = postseasonBoard({ kind_code: "A", year: 2026, away_score: 0, home_score: 3, completed: false }, 0);
  assertSituationHidden(html, "A 基準");
});

test("#237 歷史 E 2025 不受影響：snapshot=null＋比分＝終場", () => {
  const html = postseasonBoard({ kind_code: "E", year: 2025, away_score: 4, home_score: 3 }, 1);
  assertSituationHidden(html, "E 2025");
});
