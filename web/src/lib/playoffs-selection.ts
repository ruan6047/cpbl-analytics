import type { PlayoffsSeriesCode } from "./playoffs-types.ts";

export type PlayoffsQuery = Record<string, string | string[] | undefined>;
export type PlayoffsSelection = { valid: true; year: number | null; series: PlayoffsSeriesCode | null; game: number | null; revision: string | null }
  | { valid: false };

/** 指定卻無效的身分不可當作未指定，否則歷史網址會誤顯示目前場次。 */
export function parsePlayoffsSelection(query: PlayoffsQuery): PlayoffsSelection {
  const { year, series, game, revision } = query;
  if (year !== undefined && (typeof year !== "string" || !/^\d{4}$/.test(year) || +year < 1990 || +year > 2100)) return { valid: false };
  if (series !== undefined && series !== "E" && series !== "C") return { valid: false };
  if (game !== undefined && (typeof game !== "string" || !/^\d+$/.test(game) || !Number.isSafeInteger(+game) || +game < 1)) return { valid: false };
  if (revision !== undefined && (typeof revision !== "string" || !revision.trim())) return { valid: false };
  return { valid: true, year: year === undefined ? null : +year, series: series ?? null,
    game: game === undefined ? null : +game, revision: revision ?? null };
}

export function playoffsGameHref(year: number, series: string, game: number): string {
  return `/playoffs?${new URLSearchParams({ year: String(year), series, game: String(game) })}#watch`;
}

/** 路由只搬移原始身分；存在性及非法值交新版處理，不讀報告來找下一場。 */
export function legacyPlayoffsLocation(sno: string, source: URLSearchParams): string {
  const target = new URLSearchParams();
  for (const [from, to] of [["year", "year"], ["kind", "series"]]) {
    const values = source.getAll(from);
    for (const value of values.length ? values : [""]) target.append(to, value);
  }
  target.set("game", sno);
  for (const value of source.getAll("revision")) target.append("revision", value);
  return `/playoffs?${target}#watch`;
}
