import { slotGameLabel } from "../components/postseason-series.tsx";
import type { JourneySlot } from "./postseason-journey.ts";

/** 季後賽層級標記（C=台灣大賽/E=季後挑戰賽/F=二軍季後；例行賽 A/D 無標記）。 */
export const POST_LABEL: Record<string, string> = { C: "台灣大賽", E: "季後挑戰賽", F: "二軍季後" };

/**
 * 賽況月曆的季後賽對應：有資料庫列的格依「kind-sno」索引，沒有列的公告格依日期分組另畫。
 * 月曆格與日期清單共用同一份（#459），場次編號只來自後端 ``arrangement`` 綁定的格，前端不重算。
 */
export function calendarPostseasonIndex(slots: readonly JourneySlot[]) {
  const slotByRow = new Map<string, JourneySlot>();
  const announcedByDate = new Map<string, JourneySlot[]>();
  for (const s of slots) {
    if (s.row) slotByRow.set(`${s.row.kind_code}-${s.row.game_sno}`, s);
    else (announcedByDate.get(s.date) ?? announcedByDate.set(s.date, []).get(s.date)!).push(s);
  }
  return { slotByRow, announcedByDate };
}

/** 「台灣大賽 G5」：月曆格與日期清單的季後賽列標籤；非季後賽列回 null。 */
export function calendarPostseasonLabel(kindCode: string, js: JourneySlot | undefined): string | null {
  const base = POST_LABEL[kindCode];
  if (!base) return null;
  return js ? `${base} ${slotGameLabel(js)}` : base;
}
