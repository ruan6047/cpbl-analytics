import assert from "node:assert/strict";
import test from "node:test";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { MemberCard, RosterSection, RosterView } from "./roster-section.tsx";
import {
  filterMembersByPos,
  POS_FILTERS,
  rosterNotes,
  rosterPath,
  SORTS,
  drawerSubtitle,
  initialScope,
  scopeG,
  sortMembers,
  type PlayoffsRoster,
  type RosterArrow,
  type RosterMember,
  type RosterTeam,
} from "@/lib/playoffs-roster.ts";

// #286 S05 WP2：第 3 區名單（背景）呈現、篩選排序、頁尾說明。
// 篩選／排序 state 在 `RosterBody`（useState）；這裡以 `RosterView` 直接注入各組合驗呈現。

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

test("null ⇒ 第 3 區錯誤態；標題固定", () => {
  const t = text(<RosterSection data={null} />);
  assert.match(t, /系列賽 32 人資格名單/);
  assert.match(t, /第 3 區資料暫時無法讀取/);
});

test("series_unknown ⇒ 對戰組合尚未確定", () => {
  assert.match(text(<RosterSection data={payload([], "series_unknown")} />), /對戰組合尚未確定/);
});

test("小卡：守位、角色（有值才顯示）、G、二軍、無紀錄「—」、PR 標籤用球員頁同一組中文標籤", () => {
  const html = renderToStaticMarkup(<RosterView data={payload([A, B], "partial")} team="all" sort="position" />);
  const t = text(<RosterView data={payload([A, B], "partial")} team="all" sort="position" />);
  assert.match(t, /球員11 外野手 120G/);
  assert.match(t, /球員11 外野手 120G 主力 AVG/);       // 角色有值：只顯示值
  assert.doesNotMatch(t, /本站角色/);                   // PR3：不帶「本站角色」字樣
  assert.match(t, /二軍/);
  assert.match(t, /球員04 捕手 —/);
  assert.match(t, /wOBA PR 95/);
  assert.match(t, /奪三振% PR 91/);              // 投手用 pl 標籤
  assert.match(t, /AVG \.300 · OPS \.800/);
  assert.match(t, /ERA 2\.70 · 50\.0 IP/);
  assert.match(html, /data-roster-status="missing"/);
  assert.match(t, /兄弟 待更新/);               // 名單未提交：格內只留簡短狀態
});

test("G05：區內不出現 28 人、登錄、先發、可出賽等說明（只在頁尾）", () => {
  const t = text(<RosterView data={payload([A, B], "partial")} team="all" sort="position" />);
  for (const w of ["28", "登錄", "先發", "可出賽", "資格名單不", "百分位", "代跑"]) assert.ok(!t.includes(w), w);
});

test("篩選：只顯示選中球隊；排序：投手／野手分組內依出賽 G 多到少、無紀錄最後", () => {
  const t = text(<RosterView data={payload([A, B], "partial")} team="ACN011" sort="position" />);
  assert.ok(!t.includes("球員11"));
  const html = renderToStaticMarkup(<RosterView data={payload([A, B])} team="AAA011" sort="games" />);
  const order = [...html.matchAll(/data-player="(\d+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, ["0000000002", "0000000011", "0000000003", "0000000004"]);
  assert.deepEqual(sortMembers(A.members, "games").map((m) => m.player_id),
    ["0000000011", "0000000002", "0000000003", "0000000004"]);
  const byPos = sortMembers(A.members, "position").map((m) => m.player_id);
  assert.deepEqual(byPos, ["0000000002", "0000000004", "0000000003", "0000000011"]);
  assert.match(html, /aria-pressed="true"[^>]*>味全</);
});

test("頁尾說明：固定說明收進 InfoDot（notes(null) 空陣列）；依資料動態加缺名單與待送達場次", () => {
  assert.deepEqual(rosterNotes(null), []);
  const dyn = rosterNotes(payload([A, B], "partial")).map((n) => n.key);
  assert.deepEqual(dyn, ["roster.roster_missing.ACN011"]);
  assert.equal(new Set(dyn).size, dyn.length);
  const none = rosterNotes(payload([team("AAA011", "味全", [member("0000000001", "投手")])])).map((n) => n.key);
  assert.deepEqual(none, []);
  assert.ok(rosterNotes(payload([A, B], "partial")).every((n) => n.text.length <= 80));
});

test("摘要路徑", () => {
  assert.equal(rosterPath(2026, "C"), "/api/v1/playoffs/roster?season=2026&series=C");
});

test("冷熱箭頭：方向附文字（不只靠顏色）、OPS+／ERA+ 末段值；不足與 ERA0 顯示「—」", () => {
  const html = renderToStaticMarkup(<RosterView data={payload([A])} team="all" sort="position" />);
  const t = text(<RosterView data={payload([A])} team="all" sort="position" />);
  assert.match(t, /近 15 場 OPS\+ 132 ↑ 升/);
  assert.match(t, /近 15 場 ERA\+ 88 ↓ 降/);
  assert.match(html, /data-arrow="none"/);
  const z = member("0000000009", "投手", {}, { arrow: arrowOf("undefined", "pitching") });
  const tz = text(<RosterView data={payload([team("AAA011", "味全", [z])])} team="all" sort="position" />);
  assert.match(tz, /近 15 場 ERA\+ — —/);
  assert.ok(!/Infinity|999/.test(tz));
});

test("排序：箭頭方向 上升 → 平穩 → 下降 → 無箭頭", () => {
  const f = member("0000000020", "內野手", {}, { arrow: arrowOf("flat", "batting") });
  const order = sortMembers([...A.members, f], "arrow").map((m) => m.player_id);
  assert.deepEqual(order, ["0000000011", "0000000020", "0000000002", "0000000004", "0000000003"]);
});

test("每張小卡有開抽屜按鈕（aria-haspopup=dialog、帶 player_id 供焦點歸還）", () => {
  const html = renderToStaticMarkup(<RosterView data={payload([A])} team="all" sort="position" />);
  const buttons = [...html.matchAll(/<button[^>]*data-open-player="(\d+)"[^>]*>/g)];
  assert.equal(buttons.length, A.members.length);
  assert.ok(buttons.every((b) => /aria-haspopup="dialog"/.test(b[0])));
});

// —— PR2 WP7：本系列實戰切換 ————————————————————————————————————————————————

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

test("切換：後端提供系列 scope 才顯示兩個切換鈕；舊版回應（not_provided）不顯示", () => {
  assert.match(text(<RosterView data={withSeries("ok")} team="all" sort="position" />), /例行賽與對戰背景 本系列實戰數據/);
  assert.doesNotMatch(text(<RosterView data={payload([A])} team="all" sort="position" />), /本系列實戰數據/);
});

test("本系列：小卡顯示本系列 G 與計數，不顯示箭頭與 PR；未出賽 0G、無計數「—」", () => {
  const html = renderToStaticMarkup(<RosterView data={withSeries("ok")} team="AAA011" sort="position" scope="series" />);
  const t = text(<RosterView data={withSeries("ok")} team="AAA011" sort="position" scope="series" />);
  assert.match(html, /data-scope="series"/);
  assert.match(t, /球員11 外野手 3G/);
  assert.match(t, /球員02 投手 0G/);
  assert.doesNotMatch(t, /末段 15 次|PR 9|二軍/);
  assert.match(t, /球員02 投手 0G 終結 —/);   // 0G 投手：角色照顯示，計數「—」
});

test("本系列尚無完賽場：G 與計數皆「—」", () => {
  const t = text(<RosterView data={withSeries("no_games")} team="AAA011" sort="position" scope="series" />);
  assert.match(t, /球員11 外野手 —/);
});

test("box 未送達：該隊標題旁「待更新」；頁尾列場次", () => {
  const d = withSeries("pending_source", [2, 3]);
  const html = renderToStaticMarkup(<RosterView data={d} team="all" sort="position" scope="series" />);
  assert.equal((html.match(/data-series-pending/g) ?? []).length, 1);
  const n = rosterNotes(d).find((x) => x.key === "roster.series_box_pending");
  assert.equal(n?.text, "本系列第 2、3 場的逐場紀錄尚未送達，本系列實戰數據暫不含這幾場。");
  assert.ok(!rosterNotes(withSeries("ok")).some((x) => x.key === "roster.series_box_pending"));
  // 背景 scope 不顯示系列「待更新」
  assert.doesNotMatch(renderToStaticMarkup(<RosterView data={d} team="all" sort="position" scope="background" />),
    /data-series-pending/);
});

test("排序：出賽 G 依目前 scope；初始 scope 取 default_scope（T5 ⇒ 本系列），舊版回應一律背景", () => {
  const d = withSeries("ok");
  assert.deepEqual(sortMembers(d.teams[0].members, "games", "series").map((m) => m.player_id),
    ["0000000011", "0000000004", "0000000003", "0000000002"]);
  assert.equal(initialScope(withSeries("ok", [], "series")), "series");
  assert.equal(initialScope(withSeries("ok")), "background");
  const old = payload([A]); old.default_scope = "series";
  assert.equal(initialScope(old), "background");
});

test("切換保留篩選與排序：scope 不影響 team／sort 的選取狀態", () => {
  const html = renderToStaticMarkup(<RosterView data={withSeries("ok")} team="ACN011" sort="games" scope="series" />);
  assert.match(html, /aria-pressed="true"[^>]*>兄弟</);
  assert.match(html, /aria-pressed="true"[^>]*>出賽 G</);
  assert.match(html, /aria-pressed="true"[^>]*>本系列實戰數據</);
});

test("review-3 F1：本系列來源未齊的球員顯示「待更新」（⛔ 0G），背景 scope 不受影響；F2：本系列打者 line 帶 SO", () => {
  const d = withSeries("pending_source", [1]);
  const t0 = d.teams[0];
  t0.series_pending_roles = ["pitching"];
  t0.members = t0.members.map((m) => (m.role === "pitching" ? { ...m, series: { g: null, line: null, pending: true } } : m));
  const p = t0.members.find((m) => m.role === "pitching")!;
  const series = text(<MemberCard m={p} scope="series" />);
  assert.match(series, /球員02 投手 待更新/);
  assert.match(series, /球員02 投手 待更新 終結 待更新/);   // 角色有值仍顯示，計數待更新
  assert.doesNotMatch(series, /0G/);
  assert.match(text(<MemberCard m={p} scope="background" />), /球員02 投手 55G/);
  assert.equal(scopeG(p, "series"), null);
  assert.deepEqual(sortMembers(t0.members, "games", "series").at(-1)?.player_id, p.player_id);
  const b: RosterMember = { ...A.members[0], series: { g: 3, pending: false,
    line: { pa: 12, ab: 10, h: 3, hr: 1, bb: 2, so: 4, avg: 0.3, obp: 0.417, slg: 0.6, ops: 1.017 } } };
  assert.equal((b.series?.line as { so?: number }).so, 4);
});

// —— PR3：角色行（需求方裁定 #286 6210276945、6210408828） ——————————————————————————

test("PR3：角色無值整段不顯示（無 data-role、不多出「—」），有值只顯示值；其他缺值仍「—」", () => {
  const none = member("0000000041", "外野手", { tactical_role: null }, { level: "none", g: null, line: null,
    arrow: arrowOf("insufficient", "batting") });
  const html = renderToStaticMarkup(<MemberCard m={none} />);
  const t = text(<MemberCard m={none} />);
  assert.doesNotMatch(html, /data-role/);
  assert.doesNotMatch(t, /本站角色/);
  assert.equal(t, "球員41 外野手 — — 近 15 場 OPS+ — —");   // G「—」、計數「—」、箭頭「—」照舊，整卡可點不再多印按鈕字
  const withRole = member("0000000042", "投手", { tactical_role: "勝利組" });
  const html2 = renderToStaticMarkup(<MemberCard m={withRole} />);
  assert.match(html2, /<span data-role="true" class="text-ink">勝利組<\/span>/);
  assert.doesNotMatch(text(<MemberCard m={withRole} />), /本站角色/);
});

test("PR3：抽屜標頭副標——角色有值只放值、無值整段省略，不帶「本站角色」", () => {
  assert.equal(drawerSubtitle(member("0000000043", "投手", { tactical_role: "終結" }, { g: 55 })), "投手 · 終結 · 55G");
  assert.equal(drawerSubtitle(member("0000000044", "捕手", { tactical_role: null }, { g: 12 })), "捕手 · 12G");
  assert.equal(drawerSubtitle(member("0000000045", "內野手", {}, { level: "D", g: 40 })), "內野手 · 40G · 二軍");
  assert.equal(drawerSubtitle(member("0000000046", "外野手", {}, { level: "none", g: null })), "外野手 · —");
});

test("PR3：頁尾說明不受角色行改動影響（動態缺值 key 照常、不含本站角色）", () => {
  assert.deepEqual(rosterNotes(null).map((n) => n.key), []);
  assert.deepEqual(rosterNotes(payload([A, B], "partial")).map((n) => n.key), ["roster.roster_missing.ACN011"]);
  assert.ok(rosterNotes(payload([A, B], "partial")).every((n) => !n.text.includes("本站角色")));
});

test("守位篩選與排序：排序移除「守位」，新增守位篩選（全部／投手／捕手／內野手／外野手），全部時投手與野手分組", () => {
  assert.deepEqual(SORTS.map((x) => x.label), ["出賽 G", "箭頭方向"]);
  assert.deepEqual(POS_FILTERS.map((x) => x.label), ["全部", "投手", "捕手", "內野手", "外野手"]);
  const htmlAll = renderToStaticMarkup(<RosterView data={payload([A])} team="all" pos="all" sort="games" />);
  assert.match(htmlAll, /aria-pressed="true"[^>]*>出賽 G</);
  assert.match(htmlAll, /data-role-group="pitching"/);
  assert.match(htmlAll, /data-role-group="batting"/);
  assert.doesNotMatch(htmlAll, /官方守位/);
  const htmlPos = renderToStaticMarkup(<RosterView data={payload([A])} team="all" pos="內野手" sort="games" />);
  assert.doesNotMatch(htmlPos, /data-role-group="pitching"/);
  assert.deepEqual(filterMembersByPos(A.members, "內野手").map((m) => m.player_id), ["0000000003"]);
  assert.deepEqual(sortMembers(A.members, "position").map((m) => m.player_id),
    ["0000000002", "0000000004", "0000000003", "0000000011"]);
});

