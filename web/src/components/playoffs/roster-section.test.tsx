import assert from "node:assert/strict";
import test from "node:test";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { RosterBlocks, RosterSection } from "./roster-section.tsx";
import {
  battingComposite,
  dhStatus,
  drawerStatLine,
  fielderBlocks,
  pitcherBlocks,
  pitchingComposite,
  rosterNotes,
  rosterPath,
  drawerSubtitle,
  initialScope,
  memberRoles,
  scopeG,
  teamComposition,
  type PitchingLine,
  type PlayoffsRoster,
  type RosterArrow,
  type RosterMember,
  type RosterTeam,
} from "@/lib/playoffs-roster.ts";

// #286 S05 WP2：第 3 區名單呈現與頁尾說明；#350 方案 D：兩隊並列、依位置分區、每區先列綜合成績再列人名。
// 資料範圍 state 在 `RosterBody`（useState）；這裡以 `RosterBlocks` 直接注入各範圍驗呈現。

function text(node: ReactNode): string {
  return renderToStaticMarkup(<>{node}</>).replace(/<[^>]*>/g, " ").replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
}

function arrowOf(status: RosterArrow["status"], role: "batting" | "pitching", value: number | null = 112): RosterArrow {
  const ok = status === "up" || status === "down" || status === "flat";
  return { status, reason: ok ? null : status === "undefined" ? "era_zero" : "appearances",
    metric: role === "batting" ? "ops_plus" : "era_plus", appearances: ok ? 30 : 12,
    w1: ok || status === "undefined" ? { value: ok ? value : null } : null, w0: null, delta: ok ? 16.2 : null };
}

function member(id: string, pos: string, extra: Partial<RosterMember> = {},
  bg: Partial<RosterMember["background"]> = {}): RosterMember {
  const role = pos === "投手" ? "pitching" : "batting";
  return {
    player_id: id, name: `球員${id.slice(-2)}`, official_position: pos, tactical_role: null, role,
    background: {
      level: "A", g: 50, pr_tags: [], arrow: arrowOf("flat", role),
      line: role === "pitching" ? { outs: 150, ip: "50.0", er: 15, so: 40, bb: 12, era: 2.7 }
        : { pa: 200, ab: 180, h: 54, hr: 5, bb: 15, avg: 0.3, obp: 0.356, slg: 0.444, ops: 0.8 },
      ...bg,
    },
    ...extra,
  };
}

function team(code: string, name: string, members: RosterMember[], status: RosterTeam["roster_status"] = "submitted"): RosterTeam {
  return { team_code: code, team_name: name, roster_status: status, members,
    roster: status === "submitted" ? { roster_id: "r", published_date: "2026-10-16", source_url: null, annotation_version: 1 } : null };
}

function payload(teams: RosterTeam[], status: PlayoffsRoster["status"] = "ok"): PlayoffsRoster {
  return {
    contract: "playoffs-roster/v1", context_version: "ctx", series: "C", year: 2026,
    series_id: { year: 2026, kind_code: "C", teams: teams.map((t) => t.team_code) },
    as_of: { now: "", taipei_date: "2026-10-16", last_refresh_at: null, last_completed_game_date: null, background_cutoff: "2026-10-06" },
    status, default_scope: "background",
    arrow_policy: { version: "playoffs-arrow/prd-v2-proposed", status: "proposed", window: 15, bat_min_ab: 30,
      pit_min_outs: 30, ops_plus_delta: 15, era_plus_delta: 20 },
    scopes: { background: { status: "ok" }, series: { status: "not_provided" } },
    registration: { status: "unknown", reason: "registration_source_not_delivered" }, roster_version: "rv",
    teams, missing_reason: [],
  };
}

const A = team("AAA011", "味全", [
  member("0000000011", "外野手", { tactical_role: "主力" },
    { g: 120, pr_tags: [{ key: "woba_pr", value: 95 }], arrow: arrowOf("up", "batting", 131.6) }),
  member("0000000002", "投手", { tactical_role: "終結" },
    { g: 55, pr_tags: [{ key: "kp_pr", value: 91 }], arrow: arrowOf("down", "pitching", 88.4) }),
  member("0000000003", "內野手", {}, { level: "D", g: 40, arrow: arrowOf("insufficient", "batting") }),
  member("0000000004", "捕手", {}, { level: "none", g: null, line: null, arrow: arrowOf("insufficient", "batting") }),
]);
const B = team("ACN011", "兄弟", [], "missing");

function withSeries(status: PlayoffsRoster["scopes"]["series"]["status"], pending: number[] = [],
  defaultScope: PlayoffsRoster["default_scope"] = "background"): PlayoffsRoster {
  const series = (m: RosterMember, g: number) => ({ ...m, series: status === "no_games" ? null
    : { g, line: g ? m.background.line : null } });
  const t = team("AAA011", "味全", A.members.map((m, i) => series(m, [3, 0, 1, 2][i])));
  t.series_pending_games = pending;
  const d = payload([t, team("ACN011", "兄弟", [series(member("0000000031", "投手"), 2)])]);
  d.scopes.series = { status, completed_games: status === "no_games" ? 0 : 3, pending_games: pending };
  d.default_scope = defaultScope;
  return d;
}

test("null ⇒ 第 3 區錯誤態；標題固定", () => {
  const t = text(<RosterSection data={null} />);
  const markup = renderToStaticMarkup(<RosterSection data={null} />);
  assert.match(markup, /<h2 id="roster-heading"[^>]*>系列賽名單<\/h2>/);
  assert.match(markup, /aria-label="系列賽名單說明"/);
  assert.match(t, /第 3 區資料暫時無法讀取/);
});

test("series_unknown ⇒ 對戰組合尚未確定", () => {
  assert.match(text(<RosterSection data={payload([], "series_unknown")} />), /對戰組合尚未確定/);
});

test("摘要路徑", () => {
  assert.equal(rosterPath(2026, "C"), "/api/v1/playoffs/roster?season=2026&series=C");
});

test("頁尾說明：固定說明收進 InfoDot（notes(null) 空陣列）；依資料動態加缺名單與待送達場次", () => {
  assert.deepEqual(rosterNotes(null), []);
  const dyn = rosterNotes(payload([A, B], "partial")).map((n) => n.key);
  assert.deepEqual(dyn, ["roster.roster_missing.ACN011"]);
  const none = rosterNotes(payload([team("AAA011", "味全", [member("0000000001", "投手")])])).map((n) => n.key);
  assert.deepEqual(none, []);
  assert.ok(rosterNotes(payload([A, B], "partial")).every((n) => n.text.length <= 80 && !n.text.includes("本站角色")));
});

test("抽屜標頭副標——角色有值只放值、無值整段省略，不帶「本站角色」；多角色平列", () => {
  assert.equal(drawerSubtitle(member("0000000043", "投手", { tactical_role: "終結" }, { g: 55 })), "投手 · 終結 · 55G");
  assert.equal(drawerSubtitle(member("0000000044", "捕手", { tactical_role: null }, { g: 12 })), "捕手 · 12G");
  assert.equal(drawerSubtitle(member("0000000045", "內野手", {}, { level: "D", g: 40 })), "內野手 · 40G · 二軍");
  assert.equal(drawerSubtitle(member("0000000046", "外野手", {}, { level: "none", g: null })), "外野手 · —");
  const multi = member("0000000001", "內野手", { role_format_version: 2, tactical_role: null, tactical_roles: ["代打", "指定打擊"] });
  assert.match(drawerSubtitle(multi), /代打、指定打擊/);
});

test("v2 角色空值仍拋錯（⛔ 靜默當無角色）", () => {
  const bad = member("0000000050", "投手", { role_format_version: 2, tactical_roles: [] });
  assert.throws(() => memberRoles(bad), /角色v2資料不完整/);
  assert.throws(() => pitcherBlocks([team("AAA011", "味全", [bad])], "background"), /角色v2資料不完整/);
});

test("初始 scope 取 default_scope（T5 ⇒ 本系列），舊版回應一律背景", () => {
  assert.equal(initialScope(withSeries("ok", [], "series")), "series");
  assert.equal(initialScope(withSeries("ok")), "background");
  const old = payload([A]); old.default_scope = "series";
  assert.equal(initialScope(old), "background");
});

// —— #350 方案 D ————————————————————————————————————————————————————————————

const bat = (ab: number, h: number, bb: number, hbp: number, sf: number, tb: number) =>
  ({ pa: ab + bb + hbp + sf, ab, h, hr: 0, bb, hbp, sf, tb, avg: null, obp: null, slg: null, ops: null });

function fielder(id: string, primary: string | null, extra: Partial<RosterMember["background"]> = {},
  series: RosterMember["series"] = undefined): RosterMember {
  return member(id, primary?.includes("外野") ? "外野手" : primary === "捕手" ? "捕手" : "內野手", { series }, {
    positions: primary ? [{ pos: primary, g: 80 }] : [], primary_position: primary, dh_starts: 0, dh_starts_unknown: 0,
    line: bat(100, 30, 10, 2, 3, 45), ...extra,
  });
}

function pitcher(id: string, roles: string[], g = 30, line: PitchingLine = { outs: 90, ip: "30.0", er: 10, so: 20, bb: 5, era: 3 },
  series: RosterMember["series"] = undefined): RosterMember {
  return member(id, "投手", { role_format_version: 2, tactical_role: null, tactical_roles: roles, series }, { g, line });
}

function seriesPayload(teams: RosterTeam[]): PlayoffsRoster {
  const d = payload(teams);
  d.scopes.series = { status: "ok", completed_games: 3, pending_games: [] };
  return d;
}

const W = team("AAA011", "味全", [
  pitcher("1000000001", ["先發"], 25), pitcher("1000000002", ["終結", "勝利組"], 50),
  pitcher("1000000003", ["中繼"], 40),
  fielder("2000000001", "游擊手", { dh_starts: 4, positions: [{ pos: "游擊手", g: 35 }, { pos: "三壘手", g: 11 }] }),
  fielder("2000000002", "游擊手", { dh_starts: 3, positions: [{ pos: "游擊手", g: 90 }] }),
  fielder("2000000003", "捕手"),
]);
const X = team("ACN011", "兄弟", [
  pitcher("3000000001", ["先發"], 26), pitcher("3000000002", ["終結"], 45),
  fielder("4000000001", "三壘手", { dh_starts: 69 }), fielder("4000000002", "捕手"),
]);

test("兩隊並列：頂部各一行組成；每區兩欄（左右各一隊）", () => {
  const html = renderToStaticMarkup(<RosterBlocks data={payload([W, X])} />);
  const t = text(<RosterBlocks data={payload([W, X])} />);
  assert.match(t, /味全 投手 3 · 捕手 1 · 內野 2 · 外野 0/);
  assert.match(t, /兄弟 投手 2 · 捕手 1 · 內野 1 · 外野 0/);
  assert.equal(teamComposition(X), "投手 2 · 捕手 1 · 內野 1 · 外野 0");
  const blocks = [...html.matchAll(/data-block="([^"]+)"/g)].map((m) => m[1]);
  for (const b of blocks) {
    const seg = html.slice(html.indexOf(`data-block="${b}"`));
    const cols = [...seg.matchAll(/data-column="([^"]+)"/g)].slice(0, 2).map((m) => m[1]);
    assert.deepEqual(cols, ["AAA011", "ACN011"], b);
  }
});

test("區塊順序：投手依角色序、空角色省略；野手依守位序，DH 區最後；多角色投手出現在多區", () => {
  const p = pitcherBlocks([W, X], "background").map((b) => b.label);
  assert.deepEqual(p, ["先發", "中繼", "勝利組", "終結"]);           // 長中繼／拆彈組兩隊都沒有 ⇒ 省略
  const f = fielderBlocks([W, X], "background").map((b) => b.label);
  assert.deepEqual(f, ["捕手", "三壘手", "游擊手", "指定打擊（DH）"]);
  const html = renderToStaticMarkup(<RosterBlocks data={payload([W, X])} />);
  assert.equal((html.match(/data-open-player="1000000002"/g) ?? []).length, 2);   // 終結＋勝利組
});

test("野手只放主守位區（不重複）；同區依該守位出賽排序", () => {
  const ss = fielderBlocks([W, X], "background").find((b) => b.label === "游擊手")!;
  assert.deepEqual(ss.columns[0].members.map((x) => x.m.player_id), ["2000000002", "2000000001"]);   // 90G > 35G
  assert.equal(fielderBlocks([W, X], "background").filter((b) => b.label === "三壘手")[0].columns[0].members.length, 0);
});

test("綜合成績：先加總計數再算率；分母 0 ⇒「—」", () => {
  const a = fielder("5000000001", "捕手", { line: bat(10, 5, 0, 0, 0, 5) });
  const b = fielder("5000000002", "捕手", { line: bat(90, 18, 10, 0, 0, 27) });
  const c = battingComposite([a, b], "background");
  assert.equal(c.kind, "batting");
  if (c.kind === "batting") {
    assert.equal(c.avg, 23 / 100);                                    // ⛔ (0.5+0.2)/2
    assert.equal(c.ops, (23 + 10) / 110 + 32 / 100);
  }
  const z = battingComposite([fielder("5000000003", "捕手", { line: bat(0, 0, 0, 0, 0, 0) })], "background");
  assert.deepEqual(z, { kind: "batting", avg: null, ops: null });
  const pc = pitchingComposite([pitcher("6000000001", ["先發"], 1, { outs: 7, ip: "2.1", er: 3, so: 0, bb: 0, era: null }),
    pitcher("6000000002", ["先發"], 1, { outs: 0, ip: "0.0", er: 1, so: 0, bb: 0, era: null })], "background");
  assert.deepEqual(pc, { kind: "pitching", era: (4 * 27) / 7, ip: "2.1" });
  assert.deepEqual(pitchingComposite([pitcher("6000000003", ["先發"], 1, { outs: 0, ip: "0.0", er: 0, so: 0, bb: 0, era: null })],
    "background"), { kind: "pitching", era: null, ip: "0.0" });
  const t = text(<RosterBlocks data={payload([team("AAA011", "味全", [fielder("5000000003", "捕手", { line: bat(0, 0, 0, 0, 0, 0) })]),
    team("ACN011", "兄弟", [])])} />);
  assert.match(t, /AVG — · OPS —/);
});

test("綜合成績：例行賽背景不混入二軍計數（名字旁標二軍）；舊回應缺 tb／hbp／sf ⇒ OPS「—」", () => {
  const farm = fielder("5000000010", "捕手", { level: "D", line: bat(50, 25, 0, 0, 0, 25) });
  const a = fielder("5000000011", "捕手", { line: bat(50, 10, 0, 0, 0, 10) });
  const c = battingComposite([farm, a], "background");
  assert.equal(c.kind === "batting" && c.avg, 0.2);
  const html = renderToStaticMarkup(<RosterBlocks data={payload([team("AAA011", "味全", [farm, a]), team("ACN011", "兄弟", [])])} />);
  assert.equal((html.match(/data-farm/g) ?? []).length, 1);
  const old = fielder("5000000012", "捕手", { line: { pa: 10, ab: 10, h: 3, hr: 0, bb: 0, avg: 0.3, obp: 0.3, slg: 0.3, ops: 0.6 } });
  assert.deepEqual(battingComposite([old], "background"), { kind: "batting", avg: 0.3, ops: null });
});

test("DH 門檻邊界：例行賽 3 不列／4 列；本系列 0 不列／1 列；unknown 可能跨門檻 ⇒ 待更新", () => {
  const s = (dh: number | null, unknown = 0) => ({ g: 1, line: bat(4, 1, 0, 0, 0, 1), pending: false, dh_starts: dh,
    dh_starts_unknown: unknown });
  assert.equal(dhStatus(fielder("7000000001", "捕手", { dh_starts: 3 }), "background"), "out");
  assert.equal(dhStatus(fielder("7000000002", "捕手", { dh_starts: 4 }), "background"), "in");
  assert.equal(dhStatus(fielder("7000000003", "捕手", { dh_starts: 3, dh_starts_unknown: 1 }), "background"), "uncertain");
  assert.equal(dhStatus(fielder("7000000004", "捕手", {}, s(0)), "series"), "out");
  assert.equal(dhStatus(fielder("7000000005", "捕手", {}, s(1)), "series"), "in");
  assert.equal(dhStatus(fielder("7000000006", "捕手", {}, s(0, 1)), "series"), "uncertain");
  assert.equal(dhStatus(fielder("7000000007", "捕手", {}, s(null)), "series"), null);
  const u = fielder("7000000003", "捕手", { dh_starts: 3, dh_starts_unknown: 1 });
  const html = renderToStaticMarkup(<RosterBlocks data={payload([team("AAA011", "味全", [u]), team("ACN011", "兄弟", [])])} />);
  const dh = html.slice(html.indexOf('data-block="fld-DH"'));
  assert.match(dh, /data-uncertain/);
  assert.match(dh, /data-composite="pending"/);                          // ⛔ 把 unknown 當 0 算綜合
});

test("切換資料範圍：DH 區成員與門檻說明跟著改；本系列依本系列出賽排序", () => {
  const s = (g: number, dh: number) => ({ g, line: bat(g * 4, g, 0, 0, 0, g), pending: false, dh_starts: dh, dh_starts_unknown: 0 });
  const liu = fielder("8000000001", "游擊手", { dh_starts: 22 }, s(3, 2));
  const zhang = fielder("8000000002", "右外野手", { dh_starts: 2 }, s(1, 1));
  const wang = fielder("8000000003", "三壘手", { dh_starts: 69 }, s(3, 0));
  const d = seriesPayload([team("AAA011", "味全", [liu, zhang]), team("ACN011", "兄弟", [wang])]);
  const dhIds = (scope: "background" | "series") => fielderBlocks(d.teams, scope).find((b) => b.key === "fld-DH")!
    .columns.map((c) => c.members.map((x) => x.m.player_id));
  assert.deepEqual(dhIds("background"), [["8000000001"], ["8000000003"]]);
  assert.deepEqual(dhIds("series"), [["8000000001", "8000000002"], []]);
  assert.match(text(<RosterBlocks data={d} scope="background" />), /指定打擊（DH） 例行賽 DH 先發 ≥4 場/);
  assert.match(text(<RosterBlocks data={d} scope="series" />), /指定打擊（DH） 本系列 DH 先發 ≥1 場/);
  // 列入 DH 區的人仍在主守位區
  assert.ok(fielderBlocks(d.teams, "series").find((b) => b.label === "游擊手")!.columns[0].members.some((x) => x.m.player_id === "8000000001"));
});

test("本系列：來源未齊 ⇒ 該欄綜合成績「待更新」、隊名旁標待更新（⛔ 當 0）；尚無完賽場 ⇒「—」", () => {
  const pend = pitcher("9000000001", ["先發"], 20, undefined, { g: null, line: null, pending: true });
  const okp = pitcher("9000000002", ["先發"], 20, undefined, { g: 1, line: { outs: 15, ip: "5.0", er: 2, so: 3, bb: 1, era: 3.6 }, pending: false });
  const t1 = team("AAA011", "味全", [pend]); t1.series_pending_games = [2];
  const d = seriesPayload([t1, team("ACN011", "兄弟", [okp])]);
  d.scopes.series = { status: "pending_source", completed_games: 2, pending_games: [2] };
  const blk = pitcherBlocks(d.teams, "series")[0];
  assert.equal(blk.columns[0].composite.kind, "pending");
  assert.deepEqual(blk.columns[1].composite, { kind: "pitching", era: 3.6, ip: "5.0" });
  const html = renderToStaticMarkup(<RosterBlocks data={d} scope="series" />);
  assert.equal((html.match(/data-series-pending/g) ?? []).length, 1);
  assert.equal(scopeG(pend, "series"), null);
  const pendBat = fielder("9000000003", "捕手", {}, { g: null, line: null, pending: true, dh_starts: null, dh_starts_unknown: 0 });
  const dd = seriesPayload([team("AAA011", "味全", [pendBat]), team("ACN011", "兄弟", [])]);
  const dh = fielderBlocks(dd.teams, "series").find((b) => b.key === "fld-DH")!;
  assert.equal(dh.columns[0].composite.kind, "pending");
  const none = seriesPayload([team("AAA011", "味全", [pitcher("9000000004", ["先發"], 20, undefined, null)]), team("ACN011", "兄弟", [])]);
  assert.equal(pitcherBlocks(none.teams, "series")[0].columns[0].composite.kind, "empty");
  // 本系列 box 未送達：頁尾照列場次
  assert.equal(rosterNotes(d).find((x) => x.key === "roster.series_box_pending")?.text,
    "本系列第 2 場的逐場紀錄尚未送達，本系列實戰數據暫不含這幾場。");
});

test("舊回應（無 positions／dh 欄）：野手退回官方守位大類分區、無 DH 區，⛔ 拋錯", () => {
  const d = payload([A, team("ACN011", "兄弟", [member("0000000031", "外野手")])]);
  const f = fielderBlocks(d.teams, "background").map((b) => b.label);
  assert.deepEqual(f, ["捕手", "內野手", "外野手"]);
  assert.doesNotThrow(() => renderToStaticMarkup(<RosterBlocks data={d} />));
});

test("無一軍守備紀錄的野手放「其他」區，⛔ 猜守位", () => {
  const f = fielderBlocks([team("AAA011", "味全", [fielder("9100000001", null)]), team("ACN011", "兄弟", [])], "background");
  assert.deepEqual(f.map((b) => b.label), ["其他（無一軍守備紀錄）"]);
});

test("主視圖只列人名：不出現個人成績、PR、近 15 場箭頭、篩選與排序控制", () => {
  const html = renderToStaticMarkup(<RosterBlocks data={payload([A, W])} />);
  const t = text(<RosterBlocks data={payload([A, W])} />);
  for (const w of ["PR 9", "近 15 場", "↑", "球隊篩選", "守位篩選", "排序", "120G", "IP"]) assert.ok(!t.includes(w), w);
  assert.doesNotMatch(html, /data-pr=|data-arrow=/);
  const buttons = [...html.matchAll(/<button[^>]*data-open-player="(\d+)"[^>]*>/g)];
  assert.ok(buttons.length > 0 && buttons.every((b) => /aria-haspopup="dialog"/.test(b[0])));
});

test("G05：區內不出現 28 人、登錄、可出賽、資格名單說明（只在頁尾／ⓘ）", () => {
  const t = text(<RosterBlocks data={payload([A, B], "partial")} />);
  for (const w of ["28", "登錄", "可出賽", "資格名單不", "百分位"]) assert.ok(!t.includes(w), w);
  assert.match(t, /兄弟 待更新/);                                       // 名單未提交：隊列只留簡短狀態
});

test("切換：後端提供系列 scope 才顯示兩個切換鈕；舊版回應（not_provided）不顯示", () => {
  assert.match(text(<RosterBlocks data={withSeries("ok")} />), /例行賽與對戰背景 本系列實戰數據/);
  assert.doesNotMatch(text(<RosterBlocks data={payload([A])} />), /本系列實戰數據/);
  assert.match(renderToStaticMarkup(<RosterBlocks data={withSeries("ok")} scope="series" />), /data-scope="series"/);
});

test("抽屜標頭個人數值：本範圍 G、AVG·OPS 或 ERA·局數、主守位出賽、DH 先發；待更新不當 0G", () => {
  const liu = fielder("8000000001", "游擊手", { g: 70, dh_starts: 22, positions: [{ pos: "游擊手", g: 35 }],
    line: { ...bat(100, 26, 10, 0, 0, 40), avg: 0.26, ops: 0.636 } },
  { g: 3, line: { ...bat(9, 1, 0, 0, 0, 1), avg: 0.111, ops: 0.222 }, pending: false, dh_starts: 2, dh_starts_unknown: 0 });
  assert.equal(drawerStatLine(liu, "background"), "例行賽 70G · AVG .260 · OPS .636 · 游擊手 35G · DH 先發 22");
  assert.equal(drawerStatLine(liu, "series"), "本系列 3G · AVG .111 · OPS .222 · DH 先發 2");
  const p = pitcher("1000000009", ["先發"], 25, { outs: 100, ip: "33.1", er: 10, so: 1, bb: 1, era: 2.7 });
  assert.equal(drawerStatLine(p), "例行賽 25G · ERA 2.70 · 33.1 局");
  const pend = pitcher("1000000010", ["先發"], 25, undefined, { g: null, line: null, pending: true });
  assert.equal(drawerStatLine(pend, "series"), "本系列 待更新");
});

test("審核 F1：抽屜保留 DH 未知狀態，與主視圖「待更新」一致（⛔ 顯示確定場數）", () => {
  const s = (dh: number | null, unknown: number) => ({ g: 1, line: { ...bat(4, 1, 0, 0, 0, 1), avg: 0.25, ops: 0.5 },
    pending: false, dh_starts: dh, dh_starts_unknown: unknown });
  const u = fielder("8100000001", "游擊手", { g: 70, dh_starts: 3, dh_starts_unknown: 1, positions: [{ pos: "游擊手", g: 35 }],
    line: { ...bat(100, 26, 10, 0, 0, 40), avg: 0.26, ops: 0.636 } }, s(0, 1));
  assert.equal(dhStatus(u, "background"), "uncertain");
  assert.equal(drawerStatLine(u, "background"), "例行賽 70G · AVG .260 · OPS .636 · 游擊手 35G · DH 先發 3（另 1 場待更新）");
  assert.equal(drawerStatLine(u, "series"), "本系列 1G · AVG .250 · OPS .500 · DH 先發 0（另 1 場待更新）");
  const nullDh = fielder("8100000002", "捕手", {}, s(null, 0));
  assert.match(drawerStatLine(nullDh, "series"), /DH 先發 待更新$/);
  assert.doesNotMatch(drawerStatLine(fielder("8100000003", "捕手", { dh_starts: 0 }), "background"), /DH/);
});
