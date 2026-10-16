import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StandingsSeries } from "./standings-series.tsx";
import type { PostseasonSeriesContextV2 } from "@/lib/postseason-series-contract";

test("系列比分使用正式 total_wins 與讓勝，不反推逐場勝數", () => {
  const context = { year: 2026, series: { E: { sides: [
    { team_code: "ACN011", total_wins: 3, game_wins: 2, initial_wins: 1 },
    { team_code: "ADD011", total_wins: 1, game_wins: 1, initial_wins: 0 },
  ] }, C: { sides: [] } } } as unknown as PostseasonSeriesContextV2;
  const out = renderToStaticMarkup(<StandingsSeries year={2026} context={context} />);
  assert.match(out, /3<small[^>]*>含讓 1 勝/);
  assert.match(out, /兄弟/); assert.match(out, /統一/);
  assert.match(out, /series=E/); assert.match(out, /series=C/);
  assert.doesNotMatch(out, /games\/|逐場|觀戰報告/);
});
test("歷年缺值不使用當年比分，仍保留原年入口", () => {
  const out = renderToStaticMarkup(<StandingsSeries year={2024} context={null} />);
  assert.equal((out.match(/系列比分未提供/g) ?? []).length, 2);
  assert.match(out, /year=2024&amp;series=E/);
  assert.match(out, /year=2024&amp;series=C/);
});
