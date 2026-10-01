// 首頁 7:3 右欄「前一比賽日賽果」的取法（#220；#218 核可的首頁 7:3）。純函式、不碰時鐘。
//
// 為什麼右欄要另外取：左欄是今天（daily summary 的 `today`），右欄要「嚴格早於今天、最近一個
// 有完賽紀錄的比賽日」。summary 的 `latest_game_day` 是「≤ 今天、最近有完成場的那一天」——
// 今天還沒有任何完成場時它就是答案；今天已有完成場時它會指向今天，那一天正是左欄，
// 此時才需要從既有的 `/api/v1/games/calendar`（同一 kind 群：A＋季後 E／C）往前找。
// 依日期切開，同一場比賽結構上不可能同時出現在兩欄（取代舊版「今日／最近比賽日二擇一」的保證）。
//
// 日界一律用 summary 給的台北日期（`today.game_date`，今天無賽程時用 `scope.as_of`），
// **不用瀏覽器或容器時鐘**——CI 與容器是 UTC，台北 00:00–08:00 會差一天。
//
// 完賽判定：
// - summary 路徑沿用後端 `completed`（證據感知：0:0 真和局也算完賽）。
// - calendar 路徑沿用 /games 頁的判定（比分 > 0；日期已由「嚴格早於切點」限定，
//   改期到未來日期的保留賽自然排除）。calendar 沒有完賽證據欄，**0:0 真和局在這條路徑
//   會被當成無賽果**——全史僅 5 場，且只在「今天已有完成場」時才走這條路；已知限制，不另造判準。

import type { CalendarGame } from "./api.ts";
import type { DailyGame, DailySummary } from "./daily-summary.ts";

export type ResultGame = DailyGame & {
  /** 單場 MVP（calendar 的 `mvp`）；沒有就不顯示。 */
  mvp: string | null;
};

export type PreviousGameDay = {
  game_date: string;
  games: ResultGame[];
  source: "summary" | "calendar";
};

const keyOf = (kind: string, sno: number, season: number) => `${season}-${kind}-${sno}`;

/** 右欄的切點：今天的台北日期（summary 推導）。 */
export function resultsCutDate(summary: Pick<DailySummary, "today" | "scope">): string {
  return summary.today?.game_date ?? summary.scope.as_of;
}

function fromCalendar(g: CalendarGame): ResultGame {
  const scored = (g.away_score ?? 0) + (g.home_score ?? 0) > 0;
  return {
    season: g.year,
    kind_code: g.kind_code,
    game_sno: g.game_sno,
    game_date: g.game_date,
    venue: g.venue,
    away_team_code: g.away_team_code,
    away_team_name: g.away_team_name,
    away_score: scored ? g.away_score : null,
    home_team_code: g.home_team_code,
    home_team_name: g.home_team_name,
    home_score: scored ? g.home_score : null,
    completed: scored,
    delay_kind: g.delay_kind,
    orig_date: g.orig_date,
    mvp: g.mvp ?? null,
  };
}

/** 嚴格早於今天、最近一個有完賽紀錄的比賽日；找不到回 null（呼叫端顯示空態）。 */
export function previousGameDay(
  summary: Pick<DailySummary, "today" | "scope" | "latest_game_day">,
  calendar: CalendarGame[] | null,
): PreviousGameDay | null {
  const cut = resultsCutDate(summary);
  const mvpByKey = new Map<string, string | null>();
  for (const g of calendar ?? []) mvpByKey.set(keyOf(g.kind_code, g.game_sno, g.year), g.mvp ?? null);

  const latest = summary.latest_game_day;
  if (latest && latest.game_date < cut) {
    return {
      game_date: latest.game_date,
      source: "summary",
      games: latest.games.map((g) => ({ ...g, mvp: mvpByKey.get(keyOf(g.kind_code, g.game_sno, g.season)) ?? null })),
    };
  }

  if (calendar) {
    let best: string | null = null;
    for (const g of calendar) {
      if (g.game_date >= cut) continue;
      if ((g.away_score ?? 0) + (g.home_score ?? 0) <= 0) continue;
      if (best === null || g.game_date > best) best = g.game_date;
    }
    if (best !== null) {
      const day = best;
      return {
        game_date: day,
        source: "calendar",
        games: calendar.filter((g) => g.game_date === day).map(fromCalendar),
      };
    }
  }
  return null;
}
