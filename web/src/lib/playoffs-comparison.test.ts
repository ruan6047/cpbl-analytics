import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  COMPARISON_COPY, T5_COPY, comparisonBarVM, formatMetric, reasonText, scopeStatusNote, streakVM, styleTagsVM,
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

test("status notes: not started, pending source, stale, missing", () => {
  assert.equal(scopeStatusNote(p2026.scopes.series), COMPARISON_COPY.status.not_started);
  assert.equal(scopeStatusNote(p2025.scopes.series), null);
  const pending = { ...p2025.scopes.series, status: "pending_source" as const, missing_game_keys: ["2025/C/5"] };
  assert.match(scopeStatusNote(pending)!, /1 場 box 未送達/);
  assert.match(scopeStatusNote({ ...p2025.scopes.season_a, status: "stale" })!, /待更新/);
  assert.equal(scopeStatusNote({ ...p2025.scopes.season_a, status: "summary_missing" }), COMPARISON_COPY.status.summary_missing);
});

test("reasons and number formatting", () => {
  assert.equal(reasonText(["box_missing:2025/C/5", "column_null:bb"]), "欄位未知；缺 box 2025/C/5");
  assert.equal(reasonText(["zero_denominator"]), "樣本為 0");
  const ops = p2025.metric_defs.find((d) => d.key === "ops")!;
  assert.equal(formatMetric(ops, 0.69829), ".698");
  assert.equal(formatMetric(ops, 1.0234), "1.023");
  assert.equal(formatMetric(ops, null), "—");
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
  assert.ok(strings.length > 20);
  for (const s of strings) assert.doesNotMatch(s, /預測|預期|誤差/, s);
});
