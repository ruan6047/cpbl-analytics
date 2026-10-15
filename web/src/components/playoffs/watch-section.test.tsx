import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { WatchSection } from "./watch-section.tsx";
import type { Load, LoadLevel, PlayoffsWatch, WatchPitcher, WatchTeam } from "@/lib/playoffs-watch.ts";

// #289 S08 WP3：第 4 區各態文字（灰／綠／橘／紅／先發不套燈號）、4B 未發布、公告事實、名單缺。

function text(node: ReactElement): string {
  return renderToStaticMarkup(node).replace(/<[^>]*>/g, " ").replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
}

const days = (p: [number, number, number, number], complete = [true, true, true, true]) =>
  [3, 2, 1, 0].map((k, i) => ({ date: `2026-10-${String(17 - k).padStart(2, "0")}`, offset: k, pitches: p[i],
    appearances: p[i] ? 1 : 0, complete: complete[i], live: false }));

function load(level: LoadLevel, extra: Partial<Load> = {}): Load {
  return {
    policy_version: "playoffs-policy/v2.0-proposed", target_date: "2026-10-17", level, label: "", complete: level !== "unknown",
    metrics: { P0: 0, P1: 0, S2: 0, S3: 0, C: 0, Q: 0 }, c_at_least: false, triggers: [], days: days([0, 0, 0, 0]),
    incomplete: [], unattributed: [], live: false, last_pitch_date: "2026-10-12", full_rest_days: 4,
    rest_unknown_reason: null, ...extra,
  };
}

function pitcher(id: string, role: string | null, l: Load, visible = true): WatchPitcher {
  return { player_id: id, name: `投手${id}`, tactical_role: role, role_source: "本站註記（非官方數據）",
    default_visible: visible, load: l, consecutive_era: null,
    recent: [{ game_key: { year: 2026, kind_code: "E", game_sno: 4 }, date: "2026-10-12", date_trusted: true,
      role_type: "中繼", pitches: 18, outs: 3, ip: "1.0" }],
    registration: { status: "unknown", text: "未知（當場登錄來源尚未接入）" } };
}

function team(code: string, pitchers: WatchPitcher[], roster = true): WatchTeam {
  return { side: code === "ACN011" ? "away" : "home", team_code: code,
    roster_status: roster ? "submitted" : "missing",
    roster: roster ? { roster_id: "r", published_date: "2026-10-16", source_url: null, annotation_version: 1, note: "" } : null,
    roster_text: roster ? null : "32 人名單尚未提交", days: [], pitchers };
}

function watch(teams: WatchTeam[], extra: Partial<PlayoffsWatch> = {}): PlayoffsWatch {
  return {
    contract: "playoffs-watch/v1", status: "ok", policy_version: "playoffs-policy/v2.0-proposed", year: 2026, series: "C",
    series_id: null, context_version: "c", watch_version: "w", target_game_key: { year: 2026, kind_code: "C", game_sno: 1 },
    requested_game_key: null,
    as_of: { now: "2026-10-17T02:00:00Z", taipei_date: "2026-10-17", last_refresh_at: "2026-10-17T02:24:00Z",
      last_completed_game_date: "2026-10-12" },
    scope: { kinds: ["A", "E", "C", "D"], note: "近三日含一軍例行賽 A、季後 E／C 與二軍 D 已完賽正式場的投手逐場球數" },
    coverage: "complete", missing_reason: [], source_manifest: [],
    publication: { status: "not_published", reason: "s09_not_enabled", slots: [
      { slot: "A", status: "not_published", text: "賽前快照尚未發布" },
      { slot: "B", status: "not_published", text: "賽前快照尚未發布" }] },
    registration: { status: "unknown", reason: "registration_source_not_delivered", text: "未知（當場登錄來源尚未接入）" },
    announcement: { source_type: "stats_datagame", note: "原始官方公告事實；不是賽前快照", status: "missing",
      text: "先發公告尚未送達", teams: [] },
    teams, ...extra,
  };
}

test("四種燈號與先發不套燈號：顏色旁都有文字", () => {
  const t = text(<WatchSection data={watch([team("ACN011", [
    pitcher("1", "終結", load("high", { triggers: [{ metric: "P1", value: 30, threshold: 30 }] })),
    pitcher("2", "勝利組", load("medium", { triggers: [{ metric: "C", value: 2, threshold: 2 }] })),
    pitcher("3", "長中繼", load("low")),
    pitcher("4", "輪值", load("starter_exempt"), false),
  ])])} />);
  for (const s of ["高負荷", "中負荷", "低負荷", "先發投手，不套用牛棚負荷燈號", "前一日 30 球（≥30）", "連續 2 日登板（≥2）"]) {
    assert.match(t, new RegExp(s.replace(/[()（）+]/g, ".")));
  }
  assert.match(t, /playoffs-policy\/v2\.0-proposed/);
  assert.match(t, /不是健康判斷、可用性或教練調度/);
});

test("灰色：列已知球數與理由，不出觸發理由、不寫可用", () => {
  const l = load("unknown", { days: days([0, 0, 20, 0], [true, false, true, true]), triggers: [],
    metrics: { P0: 0, P1: 20, S2: null, S3: null, C: null, Q: 0 },
    incomplete: [{ date: "2026-10-15", offset: 2, reasons: ["box_missing"], text: ["該隊當日正式場已完賽，但投手逐場紀錄尚未送達"] }],
    full_rest_days: null, last_pitch_date: null, rest_unknown_reason: "box_missing" });
  const t = text(<WatchSection data={watch([team("AAA011", [pitcher("9", "終結", l)])])} />);
  assert.match(t, /未知/);
  assert.match(t, /資料不完整：10\/15 該隊當日正式場已完賽，但投手逐場紀錄尚未送達/);
  assert.match(t, /10\/16 20/);
  assert.match(t, /10\/15 0\+\?/);
  assert.doesNotMatch(t.replace("不是健康判斷、可用性或教練調度", ""), /可用|待命/);
  assert.match(t, /連續登板 無法判定/);
  assert.match(t, /完整休息 無法判定（近期資料不完整）/);
});

test("角色未標記的投手不被刪除，收在其他投手", () => {
  const html = renderToStaticMarkup(<WatchSection data={watch([team("ACN011", [
    pitcher("1", "終結", load("low")), pitcher("5", null, load("low"), false), pitcher("6", "unclassified", load("low"), false)])])} />);
  assert.match(html, /<details[^>]*>.*其他投手（.*2.*）/s);
  assert.match(text(<WatchSection data={watch([team("ACN011", [pitcher("5", null, load("low"), false)])])} />), /角色未標記/);
});

test("4B 兩格各自寫賽前快照尚未發布，不出現已鎖定樣式", () => {
  const html = renderToStaticMarkup(<WatchSection data={watch([])} />);
  assert.equal((html.match(/賽前快照尚未發布/g) ?? []).length, 2);
  assert.match(html, /data-slot="A"/);
  assert.match(html, /data-slot="B"/);
  assert.doesNotMatch(html, /已鎖定|locked/);
  assert.match(text(<WatchSection data={watch([])} />), /先發公告尚未送達/);
});

test("公告事實：單邊公告各隊獨立、帶來源與台北觀測時間", () => {
  const data = watch([], { announcement: {
    source_type: "stats_datagame", note: "原始官方公告事實；不是賽前快照", status: "partial",
    source_url: "https://stats.cpbl.com.tw/api/proxy/v1/games/2026-C-1", raw_status: "SCHEDULED",
    observed_at: "2026-10-17T08:30:00+00:00",
    teams: [
      { team_code: "ACN011", starter_status: "changed", items: [{ player_id: "0000000001", team_code: "ACN011", order: 1, pos: "CF", name: "甲" }] },
      { team_code: "AAA011", starter_status: "missing", items: [] },
    ] } });
  const t = text(<WatchSection data={data} />);
  assert.match(t, /已公告（內容有更新）/);
  assert.match(t, /尚未公告/);
  assert.match(t, /本站觀測 10\/17 16:30（台北）/);
  assert.match(t, /1\. 甲（CF）/);
  assert.match(t, /原始官方公告事實；不是賽前快照/);
});

test("名單未提交：不列投手", () => {
  const t = text(<WatchSection data={watch([team("ACN011", [], false)])} />);
  assert.match(t, /32 人名單尚未提交；不以出賽紀錄代替名單/);
  assert.doesNotMatch(t, /近期球數/);
});

test("非目前目標與讀取失敗", () => {
  assert.match(text(<WatchSection data={watch([], { status: "historical_not_published", text: "歷史賽前版本由 S09 提供，尚未發布" })} />),
    /歷史賽前版本由 S09 提供，尚未發布/);
  assert.match(text(<WatchSection data={null} />), /第 4 區資料暫時無法讀取/);
});

test("連投 ERA 並列樣本與口徑；outs=0 不可定義", () => {
  const p = pitcher("1", "勝利組", load("medium"));
  p.consecutive_era = { scope: "本季一軍例行賽（A）", appearances: 3, outs: 0, ip: "0.0", er: 1, era: null, complete: true, excluded_untrusted: 0 };
  const t = text(<WatchSection data={watch([team("ACN011", [p])])} />);
  assert.match(t, /3 場 0\.0 局 自責 1・ ERA 不可定義/);
  assert.match(t, /不代表連投導致此成績/);
});
