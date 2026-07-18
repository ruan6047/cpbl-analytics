// 洞察區版面狀態判定（UX-MATCHUP1）。
// fail-closed 是常態版面契約（PRODUCT_UX_BLUEPRINT §5.9）：四種狀態各有獨立
// 版面與文案，不得合併為泛用「資料不足」。本檔只做「呈現層判定」——所有統計
// 判定（閘門、收縮、排名）都由 API 完成，前端不得重做（T4 紅線）。
import type { InsightsResponse, Role } from "./api";

/**
 * 洞察區狀態。
 * - no_baseline：C–E 無同賽事類型官方 baseline（fail-closed #4）
 * - no_data：該範圍無官方季彙總或無對戰紀錄（洞察不適用，基礎查詢照常）
 * - low_coverage：全 scope 樣本覆蓋率未過閘門（fail-closed #1）
 * - no_prior：可用配對不足，先驗（tau²）無法估計（fail-closed #2）
 * - gated：有資料但候選未過 credibility 閘門（fail-closed #3）
 * - ok：通過全部閘門，顯示候選卡
 */
export type InsightState =
  | { kind: "no_baseline"; note: string }
  | { kind: "no_data"; note: string }
  | { kind: "low_coverage"; ratio: number; gate: number; note: string }
  | { kind: "no_prior"; note: string }
  | { kind: "gated"; eligible: number; gatedOut: number; note: string }
  | { kind: "ok"; note: string | null };

/** 四種 fail-closed 狀態（＋no_data）的標題／說明文案。禁止確定語氣（無「天敵」）。 */
export const INSIGHT_COPY = {
  no_baseline: {
    title: "此賽事類型沒有可用比較基準",
    body:
      "官方季彙總僅涵蓋一軍例行賽，季後挑戰賽與總冠軍賽沒有同賽事類型的官方 " +
      "baseline 可供比較，因此不產生洞察結論。上方基礎實績即為此賽事類型的" +
      "原始對戰樣本與範圍。",
  },
  no_data: {
    title: "此範圍沒有可用的洞察母體",
    body: "該資料範圍缺少官方季彙總或對戰紀錄，無法建立比較基準。",
  },
  low_coverage: {
    title: "可觀察樣本覆蓋率未達門檻",
    body:
      "對戰樣本相對官方生涯的可觀察打席未達門檻，且屬非隨機子集，" +
      "不產生洞察結論。基礎實績查詢不受影響。",
  },
  no_prior: {
    title: "缺少可比較母體，無法建立收縮基準",
    body:
      "此範圍可用配對樣本不足，經驗貝氏先驗無法可靠估計；" +
      "不以聯盟平均硬補基準，因此不輸出排行。",
  },
  gated: {
    title: "有對戰資料，但證據強度不足",
    body:
      "所有候選經小樣本回縮後皆未通過可信度閘門——差異可能只是雜訊，" +
      "不足以構成任何方向性結論，因此不列出排行，也不做程度較弱的暗示。",
  },
} as const;

/** 洞察卡標題：候選語氣（描述性），不用斷言式「天敵」。 */
export const INSIGHT_LABELS = {
  disadvantages: "對戰劣勢候選",
  advantages: "對戰優勢候選",
} as const;

/**
 * 由 API 回應判定洞察區狀態。判定依據全部來自 API 明示欄位
 * （kind_code／coverage.passed／method.prior_available／候選清單），
 * 前端不引入任何自創閾值。
 */
export function deriveInsightState(r: InsightsResponse): InsightState {
  const note = r.sample_note ?? "";
  if (r.kind_code !== "A") return { kind: "no_baseline", note };
  if (r.coverage === null) return { kind: "no_data", note };
  if (!r.coverage.passed) {
    return {
      kind: "low_coverage",
      ratio: r.coverage.ratio,
      gate: r.coverage.gate,
      note,
    };
  }
  if (r.method.prior_available === false) return { kind: "no_prior", note };
  if (r.advantages.length === 0 && r.disadvantages.length === 0) {
    return { kind: "gated", eligible: r.eligible, gatedOut: r.gated_out, note };
  }
  return { kind: "ok", note: r.sample_note };
}

/**
 * 把 API 的 delta（號向固定「正＝有利打者」）翻成「主角視角」：
 * 正＝有利於查詢主角。投手視角取負號，保證角色翻轉時同組對戰
 * |delta| 不變、優劣標籤鏡像（對稱性由 API 建構保證，這裡只翻呈現號向）。
 */
export function subjectDelta(role: Role, deltaShrunk: number): number {
  return role === "batting" ? deltaShrunk : -deltaShrunk;
}

/** wOBA 差顯示：主角視角帶正負號、千分位三位。 */
export function fmtDelta(role: Role, deltaShrunk: number): string {
  const v = subjectDelta(role, deltaShrunk);
  const s = v >= 0 ? "+" : "−";
  return `${s}${Math.abs(v).toFixed(3)}`;
}
