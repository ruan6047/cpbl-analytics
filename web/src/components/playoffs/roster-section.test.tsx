import assert from "node:assert/strict";
import test from "node:test";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { RosterSection, RosterView } from "./roster-section.tsx";
import {
  rosterNotes,
  rosterPath,
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

test("小卡：守位、本站角色、G、二軍、無紀錄「—」、PR 標籤用球員頁同一組中文標籤", () => {
  const html = renderToStaticMarkup(<RosterView data={payload([A, B], "partial")} team="all" sort="position" />);
  const t = text(<RosterView data={payload([A, B], "partial")} team="all" sort="position" />);
  assert.match(t, /球員11 外野手 120G/);
  assert.match(t, /本站角色： 主力/);
  assert.match(t, /本站角色： —/);
  assert.match(t, /二軍/);
  assert.match(t, /球員04 捕手 —/);
  assert.match(t, /wOBA PR 95/);
  assert.match(t, /奪三振% PR 91/);              // 投手用 pl 標籤
  assert.match(t, /打擊率 \.300 · OPS \.800/);
  assert.match(t, /防禦率 2\.70 · 50\.0 局/);
  assert.match(html, /data-roster-status="missing"/);
  assert.match(t, /兄弟 待更新/);               // 名單未提交：格內只留簡短狀態
});

test("G05：區內不出現 28 人、登錄、先發、可出賽等說明（只在頁尾）", () => {
  const t = text(<RosterView data={payload([A, B], "partial")} team="all" sort="position" />);
  for (const w of ["28", "登錄", "先發", "可出賽", "資格名單不", "百分位", "代跑"]) assert.ok(!t.includes(w), w);
});

test("篩選：只顯示選中球隊；排序：出賽 G 多到少、無紀錄最後", () => {
  const t = text(<RosterView data={payload([A, B], "partial")} team="ACN011" sort="position" />);
  assert.ok(!t.includes("球員11"));
  const html = renderToStaticMarkup(<RosterView data={payload([A, B])} team="AAA011" sort="games" />);
  const order = [...html.matchAll(/data-player="(\d+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, ["0000000011", "0000000002", "0000000003", "0000000004"]);
  const byPos = sortMembers(A.members, "position").map((m) => m.player_id);
  assert.deepEqual(byPos, ["0000000002", "0000000004", "0000000003", "0000000011"]);
  assert.match(html, /aria-pressed="true"[^>]*>味全</);
});

test("頁尾說明：notes(null) 只回固定五條、全為 roster.*；依資料加缺名單、箭頭不足與二軍", () => {
  const fixed = rosterNotes(null);
  assert.deepEqual(fixed.map((n) => n.key), ["roster.registration_unknown", "roster.eligibility_not_availability",
    "roster.appearance_g", "roster.official_pr_only", "roster.arrow_proposed"]);
  assert.match(fixed[4].text, /本站建議值/);
  assert.ok(fixed.every((n) => n.key.startsWith("roster.")));
  assert.match(fixed[0].text, /28 人登錄/);
  assert.match(fixed[1].text, /不代表當場登錄、先發或可出賽/);
  assert.equal(fixed[3].source?.url, "https://stats.cpbl.com.tw");
  const dyn = rosterNotes(payload([A, B], "partial")).map((n) => n.key);
  assert.ok(dyn.includes("roster.roster_missing.ACN011"));
  assert.ok(dyn.includes("roster.farm_background"));
  assert.ok(dyn.includes("roster.arrow_unavailable"));
  assert.equal(new Set(dyn).size, dyn.length);
  const none = rosterNotes(payload([team("AAA011", "味全", [member("0000000001", "投手")])])).map((n) => n.key);
  assert.ok(!none.includes("roster.farm_background"));
  assert.ok(!none.includes("roster.arrow_unavailable"));
  assert.ok(rosterNotes(payload([A, B])).every((n) => n.text.length <= 80));
});

test("摘要路徑", () => {
  assert.equal(rosterPath(2026, "C"), "/api/v1/playoffs/roster?season=2026&series=C");
});

test("冷熱箭頭：方向附文字（不只靠顏色）、OPS+／ERA+ 末段值；不足與 ERA0 顯示「—」", () => {
  const html = renderToStaticMarkup(<RosterView data={payload([A])} team="all" sort="position" />);
  const t = text(<RosterView data={payload([A])} team="all" sort="position" />);
  assert.match(t, /末段 15 次 OPS\+ 132 ↑ 較前 15 次上升/);
  assert.match(t, /末段 15 次 ERA\+ 88 ↓ 較前 15 次下降/);
  assert.match(html, /data-arrow="none"/);
  const z = member("0000000009", "投手", {}, { arrow: arrowOf("undefined", "pitching") });
  const tz = text(<RosterView data={payload([team("AAA011", "味全", [z])])} team="all" sort="position" />);
  assert.match(tz, /末段 15 次 ERA\+ — —/);
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
