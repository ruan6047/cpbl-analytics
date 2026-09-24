// 對手交手隊別的呈現規則（#201）。本檔不得 import React 或 runtime 依賴
// （node --experimental-strip-types 測試直跑）。
//
// 生涯對戰的隊別由 API 以逐打席證據判定（opp_team_status）；本季／區間 API 不帶
// 此欄，沿用官方隊號（#201 明列的限制）。前端只照 API 狀態呈現，不自行推論隊別。
import type { TeamStatus } from "./api";

export type Affiliation = {
  /** 要畫隊徽的 franchise／隊號。 */
  codes: string[];
  /** 隊徽旁的文字說明；null＝只畫隊徽（已確認單隊或舊路徑）。 */
  note: "多隊" | "其餘未知" | "隊別未知" | null;
};

export function teamAffiliation(
  status: TeamStatus | null | undefined,
  franchises: readonly string[] | null | undefined,
  fallbackCode: string | null | undefined,
): Affiliation {
  if (!status) return { codes: fallbackCode ? [fallbackCode] : [], note: null };
  const codes = [...(franchises ?? [])];
  if (status === "unknown" || codes.length === 0) return { codes: [], note: "隊別未知" };
  if (status === "partial") return { codes, note: "其餘未知" };
  return { codes, note: codes.length > 1 ? "多隊" : null };
}

/** 對手列的可篩選隊別：生涯取已證實集合，其他範圍沿用官方 franchise。 */
export function rowFranchises(row: {
  opp_franchises?: readonly string[] | null;
  opp_franchise?: string | null;
}): string[] {
  if (row.opp_franchises) return [...row.opp_franchises];
  return row.opp_franchise ? [row.opp_franchise] : [];
}
