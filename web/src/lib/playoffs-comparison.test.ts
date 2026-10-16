import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  COMPARISON_COPY, NOTE_COPY, T5_COPY, comparisonBarVM, comparisonNotes, comparisonPath, defaultScope, formatMetric,
  scopeStatusNote, showT5, streakVM, styleTagsVM, taipeiStamp,
  type ComparisonPayload,
} from "./playoffs-comparison.ts";

// fixture＝卡號隔離庫上的真實 2025 台灣大賽（ACN011 vs AJL011）與 2026 台灣大賽（未開打）reader 輸出。
const load = (name: string): ComparisonPayload =>
  JSON.parse(readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url), "utf8"));
const p2025 = load("playoffs_comparison_2025-C.json");
const p2026 = load("playoffs_comparison_2026-C.json");
const [L, R] = p2025.series_id.teams as string[];

test("shared scale: equal values split 50/50, better side gets the larger share, both directions", () => {
  const ops = p2025.metric_defs.find((d) => d.key === "ops")!;
  const era = p2025.metric_defs.find((d) => d.key === "era")!;
  const t = p2025.scopes.series.teams;
  const same = comparisonBarVM(ops, t[L], t[L], p2025.scopes.series.scales.ops);
  assert.equal(same.leftPct, 50);
  const o = comparisonBarVM(ops, t[L], t[R], p2025.scopes.series.scales.ops);
  const e = comparisonBarVM(era, t[L], t[R], p2025.scopes.series.scales.era);
  const lOps = t[L].metrics.ops!, rOps = t[R].metrics.ops!;
  assert.equal(o.leftPct! > 50, lOps > rOps);           // OPS 高較好
  assert.equal(e.leftPct! > 50, t[L].metrics.era! < t[R].metrics.era!);  // ERA 低較好
  for (const vm of [o, e]) assert.ok(vm.leftPct! >= 25 && vm.leftPct! <= 75);
});

test("shared scale covers both teams: domain includes every scope value (no clipping)", () => {
  for (const scope of ["season_a", "head_to_head_a", "series"] as const) {
    const s = p2025.scopes[scope];
    for (const def of p2025.metric_defs) {
      const sc = s.scales[def.key]!;
      for (const v of Object.values(s.teams)) {
        const x = v.metrics[def.key];
        if (x != null) assert.ok(x >= sc.min && x <= sc.max, `${scope}/${def.key}`);
      }
    }
  }
});

test("D2: rank chips only in season_a; h2h and series show raw + league reference without ranks", () => {
  const axes = p2025.style_axes;
  const season = styleTagsVM("season_a", p2025.scopes.season_a.teams[L], axes);
  for (const tag of season) assert.match(tag.text, /第 [12]$/);
  for (const scope of ["head_to_head_a", "series"] as const) {
    const tags = styleTagsVM(scope, p2025.scopes[scope].teams[L], axes);
    assert.equal(tags.length, 7);
    for (const tag of tags) {
      assert.doesNotMatch(tag.text, /第 \d/);
      assert.match(tag.text, /聯盟平均/);
    }
    const disc = tags.find((t) => t.axis === "discipline")!;
    assert.match(disc.text, /BB% .*K% /);
  }
  assert.ok(p2025.scopes.series.teams[L].style.speed.rank === undefined);
});

test("streaks are labelled per scope, season one as end of regular season", () => {
  assert.match(streakVM("season_a", p2025.scopes.season_a.teams[L]), /^例行賽結束時 /);
  assert.equal(streakVM("series", p2025.scopes.series.teams.AJL011), "本系列 二連勝");
  assert.equal(streakVM("series", undefined), "本系列 —");
});

test("in-area statuses are short only (cross-card footer ruling): 待更新／未開打／組合待定", () => {
  assert.equal(scopeStatusNote(p2026.scopes.series), "本系列尚未開打");
  assert.equal(scopeStatusNote(p2025.scopes.series), null);
  const pending = { ...p2025.scopes.series, status: "pending_source" as const, missing_game_keys: ["2025/C/5"] };
  assert.equal(scopeStatusNote(pending), "待更新");
  assert.equal(scopeStatusNote({ ...p2025.scopes.season_a, status: "stale" }), "待更新");
  assert.equal(scopeStatusNote({ ...p2025.scopes.season_a, status: "summary_missing" }), "待更新");
  assert.equal(scopeStatusNote({ ...p2025.scopes.head_to_head_a, status: "participants_pending" }), "對戰組合待定");
  for (const v of Object.values(COMPARISON_COPY.status)) assert.ok(v.length <= 8, v);
});

test("number formatting and direction arrows stay in cell", () => {
  const ops = p2025.metric_defs.find((d) => d.key === "ops")!;
  const era = p2025.metric_defs.find((d) => d.key === "era")!;
  assert.equal(formatMetric(ops, 0.69829), ".698");
  assert.equal(formatMetric(ops, 1.0234), "1.023");
  assert.equal(formatMetric(ops, null), "—");
  const t = p2025.scopes.series.teams;
  assert.equal(comparisonBarVM(ops, t[L], t[R], p2025.scopes.series.scales.ops).direction, "↑");
  assert.equal(comparisonBarVM(era, t[L], t[R], p2025.scopes.series.scales.era).direction, "↓");
});

test("missing metric: cell shows only —, no reason text, no bar", () => {
  const ops = p2025.metric_defs.find((d) => d.key === "ops")!;
  const left = structuredClone(p2025.scopes.series.teams[L]);
  left.metrics.ops = null;
  left.null_reasons["metric:ops"] = ["column_null:bb"];
  const vm = comparisonBarVM(ops, left, p2025.scopes.series.teams[R], p2025.scopes.series.scales.ops);
  assert.equal(vm.leftPct, null);
  assert.equal(vm.leftText, "—");
  assert.ok(!("missingNote" in vm));
});

test("defaultScope: series when it has teams, else season", () => {
  assert.equal(defaultScope(p2025), "series");
  assert.equal(defaultScope(p2026), "season_a");
  assert.equal(comparisonPath(2026, "C"), "/api/v1/playoffs/comparison?season=2026&series=C");
});

// —— 頁尾說明（#285 契約 r3 §2.4／§2.5）——

test("notes(null) returns only the fixed notes, keys unique and area-prefixed", () => {
  const fixed = comparisonNotes(null);
  assert.deepEqual(fixed.map((n) => n.key),
    ["teams.direction_legend", "teams.data_source", "teams.sample_limit", "teams.t5_side_by_side"]);
  const again = comparisonNotes(p2025).slice(0, fixed.length);
  assert.deepEqual(again, fixed); // 固定說明與依資料無關
  for (const n of [...comparisonNotes(p2025), ...comparisonNotes(p2026)]) {
    assert.match(n.key, /^teams\.[a-z0-9_]+$/);
    assert.doesNotMatch(n.text, /<|>|\*\*|\[/); // 純文字
  }
});

test("notes(data) is pure: same input gives identical output, input not mutated", () => {
  const before = JSON.stringify(p2025);
  assert.deepEqual(comparisonNotes(p2025), comparisonNotes(p2025));
  assert.equal(JSON.stringify(p2025), before);
});

test("notes(data): built-at in Taipei time from payload, no clock", () => {
  const notes = comparisonNotes(p2025);
  const built = notes.find((n) => n.key === "teams.summary_built_at")!;
  const when = taipeiStamp(p2025.scopes.season_a.source!.built_at)!;
  assert.match(when, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  assert.equal(built.text, NOTE_COPY.builtAt(when, p2025.scopes.season_a.source!.completed_games));
  assert.equal(taipeiStamp("2026-10-15T05:02:01+00:00"), "2026-10-15 13:02");
});

test("notes(data): stale, missing summary, pending source and metric — reasons go to footer", () => {
  const stale = structuredClone(p2025);
  stale.scopes.season_a.status = "stale";
  stale.scopes.season_a.source!.stale_reason = "pending_rebuild";
  assert.match(comparisonNotes(stale).find((n) => n.key === "teams.summary_stale")!.text, /來源已有更正/);
  stale.scopes.season_a.source!.stale_reason = "games_changed";
  assert.match(comparisonNotes(stale).find((n) => n.key === "teams.summary_stale")!.text, /下一次每日更新/);

  const missing = structuredClone(p2026);
  missing.scopes.season_a = { status: "summary_missing", source: null, teams: {}, scales: {}, league: null };
  const mk = comparisonNotes(missing).map((n) => n.key);
  assert.ok(mk.includes("teams.summary_missing") && !mk.includes("teams.summary_built_at"));

  const pending = structuredClone(p2025);
  pending.scopes.series.status = "pending_source";
  pending.scopes.series.missing_game_keys = ["2025/C/4", "2025/C/5"];
  pending.scopes.series.covered_game_keys = ["2025/C/1", "2025/C/2", "2025/C/3"];
  const ps = comparisonNotes(pending).find((n) => n.key === "teams.series_pending_source")!;
  assert.equal(ps.text, NOTE_COPY.seriesPending("第 4、5 場", 3));

  const metric = structuredClone(p2025);
  metric.scopes.series.teams[L].metrics.der = null;
  metric.scopes.series.teams[L].null_reasons["metric:der"] = ["zero_denominator"];
  metric.scopes.series.teams[R].metrics.der = null;
  metric.scopes.series.teams[R].null_reasons["metric:der"] = ["zero_denominator"];
  const mu = comparisonNotes(metric).filter((n) => n.key === "teams.metric_unavailable");
  assert.equal(mu.length, 1); // 同一原因多格共用一條
  assert.match(mu[0].text, /樣本為 0/);
  assert.ok(!comparisonNotes(p2025).some((n) => n.key === "teams.metric_unavailable"));
});

test("T5 and all copy carry no prediction language", () => {
  const strings: string[] = [];
  const walk = (v: unknown): void => {
    if (typeof v === "string") strings.push(v);
    else if (typeof v === "function") strings.push(String((v as (...a: unknown[]) => string)(1, 1)));
    else if (v && typeof v === "object") Object.values(v).forEach(walk);
  };
  walk(T5_COPY);
  walk(COMPARISON_COPY);
  walk(NOTE_COPY);
  for (const n of comparisonNotes(p2025)) strings.push(n.text);
  assert.ok(strings.length > 30);
  for (const s of strings) assert.doesNotMatch(s, /預測|預期|誤差/, s);
});

test("payload carries area-level status (mount contract §2): real fixtures are ok", () => {
  const allowed = new Set(["ok", "partial", "unavailable"]);
  for (const p of [p2025, p2026]) {
    assert.ok(allowed.has(p.status));
    assert.equal(p.contract, "playoffs-comparison/v1");
    assert.ok(typeof p.context_version === "string" && p.context_version.length > 0);
  }
  assert.equal(p2025.status, "ok");
  assert.equal(p2026.status, "ok"); // 本系列未開打是正常狀態
});

test("showT5: only series scope + S02 decided + both scopes with teams (審核 F1)", () => {
  assert.equal(showT5(p2025, "series"), true);                        // 真實：2025 C decided
  assert.equal(showT5(p2025, "season_a"), false);
  assert.equal(showT5(p2025, "head_to_head_a"), false);
  assert.equal(p2026.series_status, "pending");                       // 真實：2026 C 未開打
  assert.equal(showT5(p2026, "series"), false);
  // 變異（標示）：同一份 2025 真實底稿只改 series_status
  for (const st of ["active", "pending", "unknown"] as const) assert.equal(showT5({ ...p2025, series_status: st }, "series"), false, st);
  // 變異（標示）：decided 但本系列無隊伍資料 ⇒ 不顯示
  assert.equal(showT5({ ...p2026, series_status: "decided" }, "series"), false);
});
