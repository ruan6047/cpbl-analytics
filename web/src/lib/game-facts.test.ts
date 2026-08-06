import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildPaGroups, halfLabel, marginText, personName, scoreAfterPlay, signedDelta, signedWpPt,
  situationText, type PaFact,
} from "./game-facts.ts";

// ---------------------------------------------------------------------------
// 合成 livelog 列（只帶分組需要的欄位）
// ---------------------------------------------------------------------------
const row = (no: string, hitter: string | null, opts: Partial<{
  hitterName: string; pitcherName: string; change: boolean;
}> = {}) => ({
  main_event_no: no,
  hitter_acnt: hitter,
  hitter_name: opts.hitterName ?? (hitter ? `打者${hitter}` : null),
  pitcher_name: opts.pitcherName ?? "投手甲",
  is_change_player: opts.change ?? false,
});

const fact = (paIndex: number, hitterId: string, members: string[],
              opts: Partial<{ name: string; pitcher: string }> = {}): PaFact => ({
  pa_id: `pa-${paIndex}`, pa_index: paIndex, state: "ready",
  inning: 1, half: "1", outs_before: 0, bases_before: [],
  away_score_before: 0, home_score_before: 0, away_score_after: 0, home_score_after: 0,
  hitter: { player_id: hitterId, name: opts.name ?? `打者${hitterId}` },
  end_hitter: { player_id: hitterId, name: opts.name ?? `打者${hitterId}` },
  pitcher: { player_id: "P1", name: opts.pitcher ?? "投手甲" },
  result_action: "一壘安打", outcome_family: "hit",
  start_event_no: members[0], end_event_no: members[members.length - 1],
  member_event_nos: members, runs_on_play: 0, delta_re24: 0.1,
  unavailable_reason: null, garbage_time: false,
});

/** 原本內嵌在 `game-board.tsx` 的近似切法，作為「不換臉」的對照基準。 */
function legacyGroups(log: ReturnType<typeof row>[], events: number[]) {
  type Grp =
    | { kind: "pa"; hitter: string; name: string; pitcher: string; idxs: number[] }
    | { kind: "sub"; gi: number };
  const groups: Grp[] = [];
  for (const gi of events) {
    const ev = log[gi];
    if (ev.is_change_player || !ev.hitter_acnt) { groups.push({ kind: "sub", gi }); continue; }
    const last = groups[groups.length - 1];
    if (last && last.kind === "pa" && last.hitter === String(ev.hitter_acnt)) last.idxs.push(gi);
    else groups.push({ kind: "pa", hitter: String(ev.hitter_acnt), name: String(ev.hitter_name ?? ""),
                      pitcher: String(ev.pitcher_name ?? ""), idxs: [gi] });
  }
  return groups;
}

const LOG = [
  row("1", "H1"), row("2", "H1"),
  row("3", null, { change: true }),
  row("4", "H2"), row("5", "H2"), row("6", "H2"),
  row("7", "H3"),
];
const EVENTS = [0, 1, 2, 3, 4, 5, 6];

const paOnly = (groups: ReturnType<typeof buildPaGroups>) =>
  groups.filter((g): g is Extract<typeof g, { kind: "pa" }> => g.kind === "pa");

// ---------------------------------------------------------------------------
// buildPaGroups：換底不換臉
// ---------------------------------------------------------------------------
test("沒有 canonical 打席時，分組逐位元等同既有的近似切法", () => {
  const expected = legacyGroups(LOG, EVENTS);
  assert.deepEqual(buildPaGroups(LOG, EVENTS), expected);
  assert.deepEqual(buildPaGroups(LOG, EVENTS, null), expected);
  assert.deepEqual(buildPaGroups(LOG, EVENTS, []), expected);
});

test("換人列一律單獨成列", () => {
  assert.deepEqual(buildPaGroups(LOG, EVENTS)[1], { kind: "sub", gi: 2 });
});

test("有 canonical 打席時，打席中途代打合成一個打席（不切成兩段）", () => {
  // 官方 livelog 在打席中途換代打會讓 hitter_acnt 變動；近似切法會切成兩個打席，
  // canonical 依 batting_order 與球數判定為同一打席（pa_build FIX1）。
  const midPinch = [row("1", "A"), row("2", "A"), row("3", null, { change: true }), row("4", "B")];
  const idxs = [0, 1, 2, 3];
  assert.equal(legacyGroups(midPinch, idxs).filter((g) => g.kind === "pa").length, 2);

  const merged = paOnly(buildPaGroups(midPinch, idxs,
    [fact(0, "A", ["1", "2", "3", "4"], { name: "原打者" })]));
  assert.equal(merged.length, 1);
  assert.deepEqual(merged[0].idxs, [0, 1, 3]);   // 換人列仍走 sub
  assert.equal(merged[0].name, "原打者");         // 記錄歸屬打者（規則 9.15(b)）
});

test("同半局同打者二度上場（打線輪轉）不得被合併", () => {
  const twice = [row("1", "A"), row("2", "B"), row("3", "A")];
  const canonical = [fact(0, "A", ["1"]), fact(1, "B", ["2"]), fact(2, "A", ["3"])];
  assert.equal(paOnly(buildPaGroups(twice, [0, 1, 2], canonical)).length, 3);
});

test("canonical 對不到的事件列退回近似切法，不整段消失", () => {
  const partial = [row("1", "A"), row("2", "B"), row("3", "B")];
  const groups = buildPaGroups(partial, [0, 1, 2], [fact(0, "A", ["1"])]);
  assert.equal(paOnly(groups).length, 2);
  assert.deepEqual(groups.flatMap((g) => (g.kind === "pa" ? g.idxs : [g.gi])), [0, 1, 2]);
});

test("每個事件索引恰好出現一次（不遺漏、不重複）", () => {
  const canonical = [fact(0, "H1", ["1", "2"]), fact(1, "H2", ["4", "5", "6"]), fact(2, "H3", ["7"])];
  for (const f of [undefined, canonical]) {
    const flat = buildPaGroups(LOG, EVENTS, f)
      .flatMap((g) => (g.kind === "pa" ? g.idxs : [g.gi]))
      .sort((a, b) => a - b);
    assert.deepEqual(flat, EVENTS);
  }
});

// ---------------------------------------------------------------------------
// 顯示層純函式
// ---------------------------------------------------------------------------
test("halfLabel 只認官方的 1/2", () => {
  assert.equal(halfLabel("1"), "上");
  assert.equal(halfLabel("2"), "下");
  assert.equal(halfLabel(null), "");
});

test("signedDelta 帶正負號、缺值不寫成 0", () => {
  assert.equal(signedDelta(1.9366), "+1.94");
  assert.equal(signedDelta(-0.1613), "−0.16");
  assert.equal(signedDelta(0), "0.00");
  assert.equal(signedDelta(null), "—");
});

test("signedWpPt 取整數百分點（不給假精度）、缺值不寫成 0", () => {
  assert.equal(signedWpPt(0.2934), "+29pt");
  assert.equal(signedWpPt(-0.1712), "−17pt");
  assert.equal(signedWpPt(0.0049), "0pt");   // 四捨五入到 0：仍是「量測到的 0」，不是缺值
  assert.equal(signedWpPt(0), "0pt");
  assert.equal(signedWpPt(null), "—");
  // `plate_appearances` 不帶 delta_wp（undefined）→ 與 null 同樣不得印成 0
  assert.equal(signedWpPt(undefined), "—");
  assert.equal(signedWpPt(Number.NaN), "—");
});

test("situationText 給出圖示以外的文字替代（a11y）", () => {
  assert.match(situationText({ inning: 7, half: "2", outs_before: 2, bases_before: ["2", "3"] }),
    /二壘、三壘有人/);
  assert.match(situationText({ inning: 1, half: "1", outs_before: 0, bases_before: [] }), /壘上無人/);
  assert.match(situationText({ inning: 9, half: "2", outs_before: 1, bases_before: ["1", "2", "3"] }),
    /滿壘/);
});

test("marginText 平手與領先分開表述", () => {
  assert.equal(marginText({ away_score_before: 3, home_score_before: 3 }), "平手");
  assert.equal(marginText({ away_score_before: 1, home_score_before: 5 }), "5–1");
  assert.equal(marginText({ away_score_before: null, home_score_before: 2 }), "");
});

test("personName 缺名時退回 ID，不回空字串（players 表會缺當季新登錄球員）", () => {
  assert.equal(personName({ player_id: "0000007822", name: "威克" }), "威克");
  assert.equal(personName({ player_id: "0000007822", name: null }), "0000007822");
  assert.equal(personName(null), "");
});

// ---------------------------------------------------------------------------
// 得分後比分（得分標示元件用）
// ---------------------------------------------------------------------------
test("直接取終結事件的事件後比分，不做加法", () => {
  // 首球全壘打：起始列即終結列，livelog 比分欄已是得分後值。
  // 若用「打席前比分 + 進帳分數」推算會多加一次（1+2=3 vs 正確的 3）。
  assert.deepEqual(scoreAfterPlay({ away_score_after: 3, home_score_after: 1 }),
    { away: 3, home: 1 });
});

test("缺任一欄回 null，不猜——比分寧可不顯示也不能顯示錯的", () => {
  assert.equal(scoreAfterPlay({ away_score_after: null, home_score_after: 0 }), null);
  assert.equal(scoreAfterPlay({ away_score_after: 0, home_score_after: null }), null);
});

test("0:0 是合法比分，不可被當成缺值", () => {
  assert.deepEqual(scoreAfterPlay({ away_score_after: 0, home_score_after: 0 }),
    { away: 0, home: 0 });
});
