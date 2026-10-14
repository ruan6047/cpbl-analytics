import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import ReportPage, { ReportPlayerDialog, ReportPlayerPeriod } from "@/app/games/[sno]/report/report-page";
import { projectReportView } from "@/lib/report-view-model";
import type { Period, Report, ReportPlayer, ReportTab, ReportView } from "@/lib/report-types";

// 合成 fixture；真實 payload 的全量比對證據在 #272 執行報告（repo 外），這裡鎖住投影規則本身。
const period = (n: number): Period => ({ status: "available", counts: { pa: n, h: 2, hr: 1, ops: 0.9, ip: "3.0", so: 4, bb: 1, er: 0, outs: 9, extra_unread: 7 },
  sample: { pa: n, ab: n - 1 }, covered_game_keys: ["2026/E/1", "2026/E/2"], expected_game_keys: ["2026/E/1", "2026/E/2"],
  coverage_status: "complete", source: "fixture", cutoff_label: "截至E2" });
const player = (pid: string, team: string, role: "batting" | "pitching", extra: Partial<ReportPlayer> = {}): ReportPlayer => ({
  player_id: pid, team_code: team, role, name: `選手${pid}`, bats: "右打", throws: "右投",
  periods: { series: period(5), regular: period(300), opponent_regular: period(40) }, last_game: period(4),
  ability: { available: false, role }, official_pr: { pa: 300, kp: 0.21, kp_pr: 60, woba: 0.35, woba_pr: 70, unused_metric: 1 },
  traits: null, splits: [{ item_index: "R", item_name: "對右打", plate_appearances: 30, hits: 7, home_runs: 2, bb: 1, so: 9, avg: 0.233 }],
  fielding: [{ pos: "捕手", g: 50, extra: 1 } as ReportPlayer["fielding"][number]], vs_starter: { status: "missing" }, pitching_usage: null, ...extra });
const game = { year: 2026, kind_code: "E", game_sno: 2, game_date: "2026-10-10", home_team_code: "ACN011", away_team_code: "ADD011", home_score: 1, away_score: 3, venue: "洲際" };
const yPlayers = [player("0000000001", "ACN011", "batting"), player("0000000001", "ACN011", "pitching"), player("0000000002", "AAA011", "pitching"),
  player("0000000003", "AAA011", "batting"), player("0000000004", "AAA011", "pitching")];
const report: Report = { status: "ok", season: 2026, kind_code: "E", game_sno: 2, game,
  players: [player("0000000009", "ADD011", "batting")], population: [], teams: [], read_at: "2026-10-14T00:00:00Z",
  sources: [{ source: "box_pitching", source_version: "hash", reference: "/api/x", updated_at: null, fetched_at: "2026-10-12", coverage_status: "available", read_at: "r" }],
  regular_coverage: { year: 2026, kind: "A", closed_before_X: true, covered_game_keys: ["2026/A/1"] },
  comparison: { game: { year: 2026, kind_code: "C", game_sno: 1, game_date: "2026-10-17", away_team_code: "ACN011", home_team_code: "AAA011", venue: null,
      away_starter: { acnt: "0000000001", name: null, status: "announced", team_code: "ACN011" }, home_starter: { acnt: null, name: null, status: "unknown", team_code: "AAA011" } },
    kind_code: "C", series_game_keys: [], usage_cutoff_label: "近期使用", players: yPlayers, population: [], teams: [],
    watch_points: [{ team_code: "ACN011", player_id: "0000000001", origin: "series", count_line: { pa: 5, h: 2 }, question: "?" }],
    field_candidates: { AAA011: { 捕手: { status: "known", g: 50, player_ids: ["0000000004"] } } } } };
const view: ReportView = { report, journey: null, updating: false };
const preview = { kind: "C" as const, sno: 1 };
const ids = (v: ReportView) => (v.report.comparison?.players ?? []).map(p => `${p.team_code}|${p.role}|${p.player_id}`);

test("依頁籤只留畫面讀得到的選手：總覽＝觀察重點同隊同人、投手＝投手、野手＝打者＋守位圖可開啟者", () => {
  assert.deepEqual(ids(projectReportView(view, "overview")), ["ACN011|batting|0000000001", "ACN011|pitching|0000000001"]);
  assert.deepEqual(ids(projectReportView(view, "pitchers")), ["ACN011|pitching|0000000001", "AAA011|pitching|0000000002", "AAA011|pitching|0000000004"]);
  assert.deepEqual(ids(projectReportView(view, "fielders")), ["ACN011|batting|0000000001", "AAA011|batting|0000000003", "AAA011|pitching|0000000004"]);
});

test("投影後三頁籤與每位保留選手的面板、四期間標記與未投影相同", () => {
  for (const tab of ["overview", "pitchers", "fielders"] as ReportTab[]) {
    const projected = projectReportView(view, tab);
    assert.equal(renderToStaticMarkup(<ReportPage view={projected} tab={tab} preview={preview} />), renderToStaticMarkup(<ReportPage view={view} tab={tab} preview={preview} />));
    for (const p of projected.report.comparison?.players ?? []) {
      const full = yPlayers.find(f => f.player_id === p.player_id && f.role === p.role && f.team_code === p.team_code)!;
      assert.equal(renderToStaticMarkup(<ReportPlayerDialog player={p} close={() => {}} season={2026} />), renderToStaticMarkup(<ReportPlayerDialog player={full} close={() => {}} season={2026} />));
      for (const key of ["series", "regular", "opponent_regular", "usage"] as const) {
        assert.equal(renderToStaticMarkup(<ReportPlayerPeriod player={p} period={key} />), renderToStaticMarkup(<ReportPlayerPeriod player={full} period={key} />));
      }
    }
  }
});

test("移除畫面不讀的欄位，保留值不改寫", () => {
  const projected = projectReportView(view, "pitchers").report;
  assert.equal(projected.players, undefined);  // 有 comparison 時頂層 X 選手不被畫面讀
  assert.equal("journey_context" in projected, false);
  assert.deepEqual(projected.sources, [{ source: "box_pitching", reference: "/api/x", updated_at: null, fetched_at: "2026-10-12", coverage_status: "available" }]);
  assert.deepEqual(projected.regular_coverage, { year: 2026, kind: "A", closed_before_X: true });
  const p = projected.comparison!.players![0];
  assert.equal(p.periods.series.expected_game_keys, undefined);
  assert.equal(p.periods.series.covered_game_keys, undefined);
  assert.equal(p.periods.series.covered_game_count, 2);
  assert.deepEqual(Object.keys(p.periods.series.counts), ["pa", "h", "hr", "ops", "ip", "so", "bb", "er", "outs"]);
  assert.deepEqual(p.official_pr, { pa: 300, kp: 0.21, kp_pr: 60, woba: 0.35, woba_pr: 70 });
  assert.deepEqual(p.splits, [{ item_index: "R", item_name: "對右打", plate_appearances: 30, hits: 7, home_runs: 2, bb: 1, so: 9 }]);
  assert.deepEqual(p.fielding, [{ pos: "捕手", g: 50 }]);
  assert.deepEqual(projectReportView(view, "fielders").report.comparison!.players![0].splits, []);  // 打者面板不呈現左右分項
  assert.equal("sources" in projected.comparison!, false);
});

test("沒有 comparison 時保留頂層選手；非 ok 狀態原樣回傳", () => {
  const { comparison: _c, ...plain } = report;
  const projected = projectReportView({ ...view, report: plain }, "fielders");
  assert.equal(projected.report.players?.length, 1);
  const missing: ReportView = { ...view, report: { ...report, status: "not_found" } };
  assert.equal(projectReportView(missing, "overview"), missing);
});
