import type { Counts, Period, Report, ReportComparison, ReportPlayer, ReportSource, ReportTab, ReportView } from "./report-types.ts";

/**
 * #272：觀戰報告（preview）伺服器端依頁籤投影後才交給 client 元件 ReportPage。
 * 只移除該頁籤畫面讀不到的選手與欄位；保留的值、鍵順序與陣列順序一律原樣，
 * 畫面標記須與未投影時相同（以真實 payload 的 renderToStaticMarkup 比對證明）。
 * 刻意不用於 /report（非 preview）；投影在 loadReport／previewMatches 之後，不影響 Y 判定與 context_hash。
 * ⛔ 不得在此推導或改寫任何數值；ReportPage 新讀任何欄位時，須同步放寬本檔白名單並重跑等價比對。
 */

// ReportPage 讀到的 counts 鍵：CountLine（投打 full／精簡）與 WatchLine 允許清單的聯集。
const COUNT_KEYS = ["ip", "era", "whip", "h", "hr", "so", "bb", "er", "pitch_cnt", "outs",
  "pa", "ab", "r", "rbi", "sb", "avg", "obp", "slg", "ops", "xbh"];
// AbilityPanel：樣本 pa 與五項官方值及其 _pr。
const OFFICIAL_PR_KEYS = ["pa", "kp", "kp_pr", "bbp", "bbp_pr", "woba", "woba_pr", "iso", "iso_pr", "hardhitp", "hardhitp_pr"];
// 面板「本季左右打分項」（只對投手呈現）。
const SPLIT_KEYS = ["item_index", "item_name", "plate_appearances", "hits", "home_runs", "bb", "so"];
// 「資料截至與來源」清單。
const SOURCE_KEYS = ["source", "reference", "updated_at", "fetched_at", "coverage_status"];
// comparison 帶這些鍵時，ReportPage 的 displayReport 一律讀 comparison 的值，頂層同名鍵不會被讀。
const SHADOWED = ["players", "population", "teams", "watch_points", "field_candidates", "announcements", "coverage"] as const;

/** 只留原物件本來就有的鍵，依原鍵順序；缺鍵不補 undefined／null。 */
function pick<T extends object>(value: T, keys: readonly string[]): T {
  return Object.fromEntries(Object.entries(value).filter(([key]) => keys.includes(key))) as T;
}

function slimPeriod(period: Period): Period {
  const { expected_game_keys: _expected, covered_game_keys: covered, counts, ...rest } = period;
  return { ...rest, counts: pick(counts, COUNT_KEYS) as Counts, covered_game_count: covered?.length ?? period.covered_game_count };
}

function slimPlayer(player: ReportPlayer): ReportPlayer {
  return {
    ...player,
    periods: { series: slimPeriod(player.periods.series), regular: slimPeriod(player.periods.regular),
               opponent_regular: slimPeriod(player.periods.opponent_regular) },
    last_game: slimPeriod(player.last_game),
    official_pr: player.official_pr ? pick(player.official_pr, OFFICIAL_PR_KEYS) : player.official_pr,
    splits: player.role === "pitching" ? player.splits.map(split => pick(split, SPLIT_KEYS)) : [],
    fielding: player.fielding.map(f => pick(f, ["pos", "g"])),
  };
}

const teamPlayer = (team: string, pid: string) => `${team}\u0000${pid}`;
type Display = Pick<Report, "watch_points" | "field_candidates" | "announcements">;

/** 該頁籤畫面（含可開啟的選手面板）會讀到的選手：整個角色，或指定的 (team, player_id)。 */
function reachable(display: Display, tab: ReportTab): { role: ReportPlayer["role"] | null; keys: Set<string> } {
  const keys = new Set<string>();
  if (tab === "overview") {
    // 觀察重點以 (player_id, team_code) 取第一筆；同人跨角色的列全留，find 結果不變。
    for (const point of display.watch_points ?? []) keys.add(teamPlayer(point.team_code, point.player_id));
    return { role: null, keys };
  }
  if (tab === "pitchers") return { role: "pitching", keys };
  // 野手：打者全部，加上守位圖 reportFieldPlayer 可能開啟／取名的同隊同人（任何角色）。
  for (const [team, positions] of Object.entries(display.field_candidates ?? {})) {
    for (const candidate of Object.values(positions)) for (const pid of candidate.player_ids) keys.add(teamPlayer(team, pid));
  }
  for (const item of display.announcements?.lineup.items ?? []) keys.add(teamPlayer(item.team_code, item.player_id));
  return { role: "batting", keys };
}

function players(list: ReportPlayer[] | undefined, display: Display, tab: ReportTab): ReportPlayer[] | undefined {
  if (!list) return list;
  const { role, keys } = reachable(display, tab);
  return list.filter(p => p.role === role || keys.has(teamPlayer(p.team_code, p.player_id))).map(slimPlayer);
}

export function projectReportView(view: ReportView, tab: ReportTab): ReportView {
  const { report } = view;
  if (report.status !== "ok") return view;
  const comparison = report.comparison;
  // 與 ReportPage 的 displayReport 同一合併規則：comparison 的鍵覆蓋頂層。
  const display: Display = comparison ? { ...report, ...comparison } : report;
  const projected: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(report)) {
    if (key === "journey_context") continue;  // journey 已由 loadReport 算進 view.journey，ReportPage 不讀。
    if (comparison && (SHADOWED as readonly string[]).includes(key) && key in comparison) continue;
    if (key === "players") projected.players = players(report.players, display, tab);
    else if (key === "sources") projected.sources = report.sources?.map(s => pick(s, SOURCE_KEYS) as ReportSource);
    else if (key === "regular_coverage") projected.regular_coverage = report.regular_coverage && pick(report.regular_coverage, ["year", "kind", "closed_before_X"]);
    else if (key === "comparison" && comparison) {
      const y: Record<string, unknown> = {};
      for (const [ykey, yvalue] of Object.entries(comparison)) {
        // comparison 的 sources 已併入頂層 sources；regular_coverage／coverage 畫面只讀頂層或不讀。
        if (ykey === "sources" || ykey === "regular_coverage" || ykey === "coverage") continue;
        y[ykey] = ykey === "players" ? players(comparison.players, display, tab) : yvalue;
      }
      projected.comparison = y as ReportComparison;
    } else projected[key] = value;
  }
  return { ...view, report: projected as Report };
}
