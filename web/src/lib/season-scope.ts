import type { Fetched } from "./fetch-result.ts";

/** 年度清單（`/api/v1/seasons`）結果 → 頁面的年度脈絡（#441）。
 *
 *  清單取得成功：與既有規則相同，當季＝清單第一筆（空清單時沿用原本的主機年份退路）。
 *  清單取不到：`currentYear` 為 null（未知）。網址沒指定年份時，呼叫端應省略 season，讓端點回
 *  正式預設年，再以成功回應的 season 呈現；網址有指定年份時照原合法化規則使用該年。
 *  ⛔ 不用主機今年或硬編年份冒充 API 當季，也⛔ 不把未知判成歷史年。 */
export type SeasonScope = {
  years: number[];
  yearsFailed: boolean;
  /** 當季；null＝年度清單取不到而無從得知。 */
  currentYear: number | null;
  /** 所選年份；null＝未指定且當季未知（呼叫端省略 season）。 */
  selectedYear: number | null;
  /** 是否為當季。未知時只在「未指定年份」成立（端點省略 season 即回當季）。 */
  isCurrentYear: boolean;
  /** 當季與否是否確定；不確定時頁面不應寫出「本季／歷年」這類判斷。 */
  currentKnown: boolean;
};

export function seasonScope(yearsR: Fetched<{ years: number[] }>, yearParam: string | undefined): SeasonScope {
  const explicit = yearParam ? Number(yearParam) : null;
  if (yearsR.ok) {
    const years = yearsR.data.years;
    const currentYear = years[0] ?? new Date().getFullYear();
    const selectedYear = explicit ?? currentYear;
    return { years, yearsFailed: false, currentYear, selectedYear, isCurrentYear: selectedYear === currentYear, currentKnown: true };
  }
  return {
    years: [], yearsFailed: true, currentYear: null, selectedYear: explicit,
    isCurrentYear: explicit == null, currentKnown: explicit == null,
  };
}
